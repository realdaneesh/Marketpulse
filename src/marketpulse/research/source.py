"""Bounded, read-only frozen source capture. Never opens the ingestion repository."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.cross_asset.config import SYMBOLS, CrossAssetConfig
from marketpulse.persistence.analytics import stamp
from marketpulse.research.models import ResearchConfig, identity


def capture(
    path: Path,
    source: str,
    cross: str | None,
    start: datetime,
    end: datetime,
    config: ResearchConfig,
) -> dict:
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Require aware start < end")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        row = db.execute(
            "SELECT config_json FROM analytics_profiles WHERE profile_id=?", (source,)
        ).fetchone()
        if row is None:
            raise ValueError("Source profile does not exist")
        policy = AnalyticsConfig.model_validate_json(row[0])
        policy_json = row[0]
        if policy.profile_id != source:
            raise ValueError("Source policy identity mismatch")
        seconds = policy.window_seconds
        intervals = (end - start).total_seconds() / seconds
        if not intervals.is_integer() or not 1 <= intervals <= config.max_intervals:
            raise ValueError("Range must contain 1..max_intervals complete grid intervals")
        if start.timestamp() % seconds or end.timestamp() % seconds:
            raise ValueError("Range boundaries must be UTC epoch grid aligned")
        for symbol in SYMBOLS:
            state = db.execute(
                "SELECT finalized_end FROM analytics_symbol_state WHERE profile_id=? AND symbol=?",
                (source, symbol),
            ).fetchone()
            if not state or not state[0] or datetime.fromisoformat(state[0]) < end:
                raise ValueError(f"{symbol} has not finalized through requested end")
        cross_policy = None
        if cross:
            row = db.execute(
                "SELECT config_json,source_profile_id FROM cross_profiles WHERE profile_id=?",
                (cross,),
            ).fetchone()
            if not row or row[1] != source:
                raise ValueError("Cross profile must reference selected source")
            cross_policy = CrossAssetConfig.model_validate_json(row[0])
            if cross_policy.profile_id(source, seconds) != cross:
                raise ValueError("Cross policy identity mismatch")
        context = max(
            policy.history_size,
            (cross_policy.lookback + cross_policy.max_lag + 2) if cross_policy else 0,
        )
        candles = []
        for symbol in SYMBOLS:
            prior = db.execute(
                "SELECT * FROM market_windows WHERE profile_id=? AND symbol=? "
                "AND window_start<? ORDER BY window_start DESC LIMIT ?",
                (source, symbol, stamp(start), context),
            ).fetchall()
            current = db.execute(
                "SELECT * FROM market_windows WHERE profile_id=? AND symbol=? "
                "AND window_start>=? AND window_start<? AND window_end<=? "
                "ORDER BY window_start LIMIT ?",
                (source, symbol, stamp(start), stamp(end), stamp(end), config.max_intervals + 1),
            ).fetchall()
            if len(current) > config.max_intervals:
                raise ValueError("Source exceeds bounded grid size")
            for item in [*reversed(prior), *current]:
                record = dict(item)
                record["detectors"] = [
                    r[0]
                    for r in db.execute(
                        "SELECT result_json FROM detector_results "
                        "WHERE window_id=? ORDER BY detector",
                        (item["id"],),
                    )
                ]
                candles.append(record)
        snapshots = []
        if cross_policy:
            snapshots = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM cross_snapshots WHERE profile_id=? AND window_end<=? "
                    "ORDER BY window_end DESC LIMIT ?",
                    (cross, stamp(end), int(intervals) + cross_policy.baseline_windows),
                )
            ]
            snapshots.reverse()
            # The bounded preceding baseline is enough; ignore older history.
            prior = [r for r in snapshots if datetime.fromisoformat(r["window_end"]) <= start]
            snapshots = [
                *prior[-cross_policy.baseline_windows :],
                *[r for r in snapshots if datetime.fromisoformat(r["window_end"]) > start],
            ]
        return dict(
            source_profile_id=source,
            cross_profile_id=cross,
            source_config=policy.model_dump(mode="json"),
            source_config_json=policy_json,
            cross_config=cross_policy.model_dump(mode="json") if cross_policy else None,
            start=stamp(start),
            end=stamp(end),
            seconds=seconds,
            candles=sorted(candles, key=lambda c: (c["window_start"], c["symbol"])),
            snapshots=snapshots,
        )
    finally:
        db.close()


def fingerprint(inputs: dict) -> str:
    return identity(inputs)


def embargo(inputs: dict) -> int:
    p, c = inputs["source_config"], inputs["cross_config"]
    return max(
        p["history_size"] + 1, c["lookback"] + c["baseline_windows"] + c["max_lag"] + 2 if c else 0
    )


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def tasks(inputs: dict) -> list[tuple[str, dict]]:
    start, end = at(inputs["start"]), at(inputs["end"])
    rows = [
        ("candle", r)
        for r in inputs["candles"]
        if at(r["window_start"]) >= start and at(r["window_end"]) <= end
    ]
    rows += [("cross", r) for r in inputs["snapshots"] if start < at(r["window_end"]) <= end]
    return sorted(rows, key=lambda item: (item[1]["window_end"], item[0], item[1]["id"]))


def context_lower(time: datetime, inputs: dict) -> datetime:
    c = inputs["cross_config"]
    return time - timedelta(seconds=inputs["seconds"] * (c["lookback"] + c["max_lag"] + 1))
