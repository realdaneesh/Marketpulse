"""Bounded experiment summaries; inferential support is distinct from descriptive output."""

import math
from collections import defaultdict
from datetime import timedelta
from itertools import permutations

from marketpulse.cross_asset.config import SYMBOLS
from marketpulse.research.design import Cusum, segment
from marketpulse.research.models import (
    ChangePoint,
    Discovery,
    Metric,
    ResearchConfig,
    Results,
    identity,
)
from marketpulse.research.reliability import adjust, sequence
from marketpulse.research.source import at, embargo


def analyze(experiment_id: str, rows: list[dict], inputs: dict, config: ResearchConfig) -> Results:
    seconds, start, end = inputs["seconds"], at(inputs["start"]), at(inputs["end"])
    count = int((end - start).total_seconds() / seconds)
    folds = [segment(i, count, embargo(inputs)) for i in range(count)]
    fold_counts = {fold: folds.count(fold) for fold in ("train", "validation", "test", "embargo")}
    records = defaultdict(list)
    features = defaultdict(list)
    binary = {s: {} for s in SYMBOLS}
    alert_times = defaultdict(set)
    for row in rows:
        time, fold, entity = at(row["time"]), row["segment"], row["entity"]
        if row["kind"] == "candle":
            c = row["candle"]
            ready = all(r["status"] == "ready" for r in row["results"])
            if ready:
                binary[entity][time] = (fold, any(r["is_anomaly"] for r in row["results"]))
            flags = [r["detector"] for r in row["results"] if r["is_anomaly"]]
            for r in row["results"]:
                records[(r["detector"], entity, fold)].append((time, r, flags))
                if r["is_anomaly"]:
                    alert_times[entity].add(time)
            eligible = c["quality"] == "observed"
            quote = float(c["quote_volume"]) if c["quote_volume"] is not None else None
            values = {
                "log_quote_volume": math.log(quote) if quote and quote > 0 else None,
                "realized_volatility": c["realized_volatility"],
                "signed_imbalance": c["signed_imbalance"],
            }
            policy = inputs["source_config"]
            if c["trade_count"] < policy["min_imbalance_trades"] or (
                quote is None or quote < policy["min_imbalance_quote_volume"]
            ):
                values["signed_imbalance"] = None
            for name, value in values.items():
                features[(entity, name)].append(
                    (time, fold, value if eligible else None, row["source_id"])
                )
        else:
            snap = row["snapshot"]
            for p, b in zip(snap["pairs"], snap["breakdowns"], strict=True):
                pair = p["asset_a"] + "-" + p["asset_b"]
                r = dict(
                    status=b["status"], is_anomaly=b["is_event"], anomaly_score=b["deviation_score"]
                )
                records[("correlation_breakdown", pair, fold)].append((time, r, []))
                features[(pair, "correlation")].append(
                    (
                        time,
                        fold,
                        p["coefficient"] if p["status"] == "ready" else None,
                        row["source_id"],
                    )
                )
                if b["is_event"]:
                    alert_times[pair].add(time)
    metrics = []
    for (name, entity, fold), samples in sorted(records.items()):
        eligible = sum(r["status"] == "ready" for _, r, _ in samples)
        alerts = sum(r["is_anomaly"] for _, r, _ in samples)
        warmup = sum(r["status"] == "insufficient_history" for _, r, _ in samples)
        histogram = [0] * 20
        durations = []
        last = None
        overlap = defaultdict(int)
        for time, r, flags in sorted(samples):
            score = r["anomaly_score"]
            if score is not None:
                histogram[min(19, max(0, int(score / 5)))] += 1
            if r["is_anomaly"]:
                if last is not None and (time - last).total_seconds() == seconds:
                    durations[-1] += seconds
                else:
                    durations.append(seconds)
                last = time
                for other in flags:
                    if other != name:
                        overlap[other] += 1
            else:
                last = None
        expected = fold_counts[fold]
        metrics.append(
            Metric(
                detector=name,
                entity=entity,
                segment=fold,
                evaluated=len(samples),
                eligible=eligible,
                alerts=alerts,
                frequency=alerts / eligible if eligible else None,
                warmup_excluded=warmup,
                coverage_excluded=max(0, expected - eligible - warmup),
                expected_intervals=expected,
                eligible_coverage=eligible / expected if expected else 0,
                episodes=len(durations),
                episode_durations_seconds=durations,
                score_histogram=histogram,
                overlap=dict(overlap),
            )
        )
    changes, sensitivity = [], {}
    variants = {
        "primary": config,
        "primary_development": config,
        "longer_initialization": config.model_copy(
            update={"initialization": config.initialization + 15}
        ),
        "higher_threshold": config.model_copy(update={"threshold": config.threshold * 1.25}),
        "post_gap_guard": config,
    }
    floors = {
        "log_quote_volume": 0.05,
        "realized_volatility": 1e-6,
        "signed_imbalance": 0.01,
        "correlation": 0.05,
    }
    for variant, cfg in variants.items():
        total = 0
        for (entity, feature), samples in sorted(features.items()):
            engine = Cusum(cfg, floors[feature])
            last, contiguous = None, 0
            for time, fold, value, reference in sorted(samples):
                # Sensitivity is predeclared and restricted to development folds.
                if variant != "primary" and fold not in ("train", "validation"):
                    continue
                contiguous = (
                    contiguous + 1 if last and (time - last).total_seconds() == seconds else 1
                )
                last = time if value is not None else None
                guarded = None if variant == "post_gap_guard" and contiguous <= 5 else value
                result = engine.step(time, guarded, fold, seconds)
                if result is None:
                    continue
                total += 1
                if variant != "primary":
                    continue
                changes.append(
                    ChangePoint(
                        id=identity([experiment_id, entity, feature, time.isoformat(), "cusum"]),
                        experiment_id=experiment_id,
                        entity=entity,
                        feature=feature,
                        segment=fold,
                        start=time - timedelta(seconds=seconds * (config.persistence - 1)),
                        end=time,
                        threshold=config.threshold,
                        evidence=[reference],
                        production_alert_nearby=any(
                            0 <= (time - t).total_seconds() <= seconds * config.max_lag
                            for t in alert_times[entity]
                        ),
                        explanation=(
                            "Two-sided robust CUSUM with a frozen preceding median/MAD "
                            "baseline, clipped standardized increments and persistent "
                            "minimum effect. Reset after flag, missing data or fold change. "
                            "Heuristic descriptive change; no significance claim."
                        ),
                        **result,
                    )
                )
        sensitivity[variant] = total
    sequences = []
    for fold in ("train", "validation", "test"):
        for a, b in permutations(SYMBOLS, 2):
            runs = []
            last = None
            for time in sorted(binary[a].keys() & binary[b].keys()):
                fa, va = binary[a][time]
                fb, vb = binary[b][time]
                if fa != fold or fb != fold:
                    continue
                if last is None or (time - last).total_seconds() != seconds:
                    runs.append(([], []))
                runs[-1][0].append(va)
                runs[-1][1].append(vb)
                last = time
            sequences.append(
                sequence(
                    a,
                    b,
                    fold,
                    runs,
                    fold_counts[fold],
                    config,
                    inputs["source_config"]["history_size"] + 1,
                )
            )
    # Six predeclared ordered hypotheses in each fold, including unavailable ones.
    for fold in ("train", "validation", "test"):
        indices = [i for i, s in enumerate(sequences) if s.segment == fold]
        corrected = adjust([sequences[i].p_value for i in indices])
        for i, q in zip(indices, corrected, strict=True):
            s = sequences[i]
            selected = all(
                any(
                    x.leader == s.leader
                    and x.follower == s.follower
                    and x.segment == f
                    and x.effect is not None
                    and x.effect >= 0.1
                    and x.status != "insufficient_data"
                    for x in sequences
                )
                for f in ("train", "validation")
            )
            confirmed = (
                fold == "test"
                and selected
                and q is not None
                and q <= config.alpha
                and s.interval is not None
                and s.interval[0] > 0
                and s.effect is not None
                and s.effect >= 0.1
            )
            sequences[i] = s.model_copy(
                update={
                    "adjusted_p": q,
                    "selected_on_training": selected,
                    "status": "held_out_association" if confirmed else s.status,
                }
            )
    discoveries = [
        Discovery(
            id=identity([c.id, "discovery"]),
            experiment_id=experiment_id,
            type=c.feature + "_shift",
            assets=c.entity.split("-"),
            start=c.start,
            end=c.end,
            observations=c.observations,
            baseline=c.baseline,
            effect=c.effect,
            statistical_readiness="descriptive_only",
            coverage=1.0,
            method="robust_two_sided_cusum",
            config_version=config.algorithm_version,
            validation="exploratory",
            evidence=[c.id, *c.evidence],
            limitations=[
                "Heuristic threshold; no calibrated p-value or probability.",
                "Observed source coverage is not exchange-certified.",
                "Replay is observational; no independent event labels.",
                "Nearby production flags are descriptive temporal overlap only.",
            ],
            explanation=c.explanation,
        )
        for c in changes
    ]
    for s in sequences:
        if s.status == "held_out_association":
            discoveries.append(
                Discovery(
                    id=identity([experiment_id, s.leader, s.follower, "heldout"]),
                    experiment_id=experiment_id,
                    type="event_sequence_association",
                    assets=[s.leader, s.follower],
                    start=start,
                    end=end,
                    observations=s.opportunities,
                    baseline=s.baseline_rate,
                    effect=s.effect,
                    statistical_readiness="assumption_dependent_holdout",
                    coverage=s.coverage,
                    method="chronological_block_bootstrap_block_permutation_BY",
                    config_version=config.algorithm_version,
                    validation="held_out_association",
                    evidence=[f"sequence:{s.leader}:{s.follower}:test"],
                    limitations=[s.explanation, "Independent external replication still required."],
                    explanation="Preselected development association retained a positive held-out "
                    "effect and BY-adjusted surrogate support under stated assumptions.",
                )
            )
    return Results(
        metrics=metrics,
        change_points=changes,
        sequences=sequences,
        discoveries=discoveries,
        sensitivity=sensitivity,
    )
