"""Single-step observational replay, including the actual preceding production context."""

import json
from bisect import bisect_left

from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.analytics.detectors import evaluate_detectors
from marketpulse.analytics.models import Candle, RiskAssessment
from marketpulse.analytics.scoring import combine_results
from marketpulse.cross_asset.config import SYMBOLS, CrossAssetConfig
from marketpulse.cross_asset.engine import evaluate
from marketpulse.cross_asset.models import CrossSnapshot
from marketpulse.research.design import segment
from marketpulse.research.source import at, context_lower, embargo


class ReplayContext:
    """Batch-local indexes and lazy models avoid quadratic preceding-history parsing."""

    def __init__(self, inputs: dict):
        self.rows = {s: [r for r in inputs["candles"] if r["symbol"] == s] for s in SYMBOLS}
        self.times = {s: [at(r["window_start"]) for r in rows] for s, rows in self.rows.items()}
        self.snapshots = inputs["snapshots"]
        self.snapshot_times = [at(r["window_end"]) for r in self.snapshots]
        self.candle_cache = {}
        self.snapshot_cache = {}

    def candle(self, row):
        if row["id"] not in self.candle_cache:
            self.candle_cache[row["id"]] = Candle.model_validate_json(row["candle_json"])
        return self.candle_cache[row["id"]]

    def snapshot(self, row):
        if row["id"] not in self.snapshot_cache:
            self.snapshot_cache[row["id"]] = CrossSnapshot.model_validate_json(row["result_json"])
        return self.snapshot_cache[row["id"]]


def replay(kind: str, row: dict, inputs: dict, context: ReplayContext | None = None) -> dict:
    context = context or ReplayContext(inputs)
    seconds = inputs["seconds"]
    index = int((at(row["window_end"]) - at(inputs["start"])).total_seconds() / seconds) - 1
    count = int((at(inputs["end"]) - at(inputs["start"])).total_seconds() / seconds)
    common = dict(
        kind=kind,
        source_id=row["id"],
        time=row["window_end"],
        segment=segment(index, count, embargo(inputs)),
        differences=[],
    )
    if kind == "candle":
        candle = context.candle(row)
        policy = AnalyticsConfig.model_validate_json(inputs["source_config_json"])
        stop = bisect_left(context.times[candle.symbol], candle.window_start)
        prior = [
            context.candle(r)
            for r in context.rows[candle.symbol][max(0, stop - policy.history_size) : stop]
        ]
        results = evaluate_detectors(candle, prior, policy)
        risk = combine_results(results, policy)
        expected = {json.loads(r)["detector"]: json.loads(r) for r in row["detectors"]}
        actual = {r.detector: r.model_dump(mode="json") for r in results}
        common["differences"] = [
            name
            for name in sorted(set(expected) | set(actual))
            if expected.get(name) != actual.get(name)
        ]
        if risk != RiskAssessment.model_validate_json(row["risk_json"]):
            common["differences"].append("risk")
        return dict(
            **common,
            entity=candle.symbol,
            candle=candle.model_dump(mode="json"),
            results=[r.model_dump(mode="json") for r in results],
        )
    expected = context.snapshot(row)
    policy = CrossAssetConfig.model_validate(inputs["cross_config"])
    time = expected.window_end
    candles = []
    for symbol in SYMBOLS:
        lo = bisect_left(context.times[symbol], context_lower(time, inputs))
        hi = bisect_left(context.times[symbol], time)
        candles.extend(context.candle(r) for r in context.rows[symbol][lo:hi])
    stop = bisect_left(context.snapshot_times, time)
    history = [
        context.snapshot(r)
        for r in context.snapshots[max(0, stop - policy.baseline_windows) : stop]
    ]
    result = evaluate(candles, history, time, inputs["source_profile_id"], seconds, policy)
    # Compaction is a worker scheduling attribute, not a statistical calculation.
    result = result.model_copy(update={"skipped_intervals": expected.skipped_intervals})
    common["differences"] = [
        key
        for key, value in result.model_dump(mode="json").items()
        if expected.model_dump(mode="json")[key] != value
    ]
    return dict(**common, entity="cross", snapshot=result.model_dump(mode="json"))
