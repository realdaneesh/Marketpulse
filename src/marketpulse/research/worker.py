"""Finite, resumable research jobs; source reads never alter production observations."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from marketpulse.research.analysis import analyze
from marketpulse.research.models import Experiment, ResearchConfig, canonical, identity
from marketpulse.research.replay import ReplayContext, replay
from marketpulse.research.source import at, capture, embargo, fingerprint, tasks


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    if db.execute("PRAGMA user_version").fetchone()[0] != 4:
        db.close()
        raise RuntimeError("Research schema is not installed; explicit migration required")
    return db


def prepare(
    store: Path,
    source_path: Path,
    source_profile: str,
    cross_profile: str | None,
    start: datetime,
    end: datetime,
    config: ResearchConfig,
) -> Experiment:
    inputs = capture(source_path, source_profile, cross_profile, start, end, config)
    digest = fingerprint(inputs)
    profile = identity([config.model_dump(mode="json"), source_profile, cross_profile])
    experiment_id = identity([profile, digest])
    db = connect(store)
    try:
        try:
            row = db.execute(
                "SELECT experiment_json FROM research_experiments WHERE id=?", (experiment_id,)
            ).fetchone()
            if row:
                return Experiment.model_validate_json(row[0])
            experiment = Experiment(
                id=experiment_id,
                profile_id=profile,
                source_profile_id=source_profile,
                cross_profile_id=cross_profile,
                algorithm_version=config.algorithm_version,
                fingerprint=digest,
                start=at(inputs["start"]),
                end=at(inputs["end"]),
                created_at=datetime.now(UTC),
                state="pending",
                cursor=0,
                total=len(tasks(inputs)),
                config=config,
                embargo_intervals=embargo(inputs),
            )
            db.execute(
                "INSERT INTO research_experiments(id,experiment_json,inputs_json) "
                "VALUES (?,?,?) ON CONFLICT(id) DO NOTHING",
                (experiment_id, experiment.model_dump_json(), canonical(inputs)),
            )
            db.commit()
            return Experiment.model_validate_json(
                db.execute(
                    "SELECT experiment_json FROM research_experiments WHERE id=?", (experiment_id,)
                ).fetchone()[0]
            )
        finally:
            db.close()
    except BaseException:
        raise


def step(store: Path, experiment_id: str, batch: int = 128) -> Experiment:
    if not 1 <= batch <= 512:
        raise ValueError("Batch must be 1..512")
    db = connect(store)
    try:
        row = db.execute(
            "SELECT * FROM research_experiments WHERE id=?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Unknown experiment")
        previous = row["experiment_json"]
        state = Experiment.model_validate_json(previous)
        if state.state in ("complete", "failed"):
            return state
        inputs = json.loads(row["inputs_json"])
        if fingerprint(inputs) != state.fingerprint:
            raise RuntimeError("Frozen research inputs failed fingerprint verification")
        work = tasks(inputs)
        context = ReplayContext(inputs)
        evaluations = [
            replay(kind, item, inputs, context)
            for kind, item in work[state.cursor : state.cursor + batch]
        ]
        updated = state.model_copy(
            update={
                "state": "running",
                "cursor": state.cursor + len(evaluations),
                "discrepancies": state.discrepancies
                + sum(bool(r["differences"]) for r in evaluations),
            }
        )
        results = None
        if updated.cursor == state.total:
            past = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT result_json FROM research_evaluations "
                    "WHERE experiment_id=? ORDER BY position",
                    (experiment_id,),
                )
            ]
            results = analyze(experiment_id, past + evaluations, inputs, state.config)
            updated = updated.model_copy(
                update={
                    "state": "complete",
                    "completed_at": datetime.now(UTC),
                    "sensitivity": results.sensitivity,
                }
            )
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT experiment_json FROM research_experiments WHERE id=?", (experiment_id,)
        ).fetchone()[0]
        if current != previous:
            raise RuntimeError("Competing research worker advanced this experiment")
        for position, value in enumerate(evaluations, state.cursor):
            db.execute(
                "INSERT INTO research_evaluations VALUES (?,?,?)",
                (experiment_id, position, canonical(value)),
            )
        if results is not None:
            for table, values in (
                ("research_metrics", results.metrics),
                ("research_sequences", results.sequences),
            ):
                db.executemany(
                    f"INSERT INTO {table} VALUES (?,?,?)",
                    [(experiment_id, i, r.model_dump_json()) for i, r in enumerate(values)],
                )
            for table, values in (
                ("research_change_points", results.change_points),
                ("research_discoveries", results.discoveries),
            ):
                db.executemany(
                    f"INSERT INTO {table}(id,experiment_id,result_json) VALUES (?,?,?)",
                    [(r.id, experiment_id, r.model_dump_json()) for r in values],
                )
        db.execute(
            "UPDATE research_experiments SET experiment_json=?,results_json=? WHERE id=?",
            (
                updated.model_dump_json(),
                results.model_dump_json() if results else None,
                experiment_id,
            ),
        )
        db.commit()
        return updated
    except BaseException as exc:
        db.rollback()
        # Atomic failure record, preserving the last committed checkpoint for diagnosis.
        if isinstance(exc, Exception) and "state" in locals() and "previous" in locals():
            failed = state.model_copy(update={"state": "failed", "error": str(exc)})
            db.execute(
                "UPDATE research_experiments SET experiment_json=? "
                "WHERE id=? AND experiment_json=?",
                (failed.model_dump_json(), experiment_id, previous),
            )
            db.commit()
        raise
    finally:
        db.close()
