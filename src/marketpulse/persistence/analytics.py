"""Checkpointed analytics persistence, with all SQL and computation off the event loop."""

import hashlib
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from marketpulse.analytics.aggregation import window_start
from marketpulse.analytics.config import AnalyticsConfig
from marketpulse.analytics.models import (
    AnomalyEvent,
    AnomalySummary,
    Candle,
    DetectorResult,
    Evaluation,
    LatestAnalytics,
    RiskAssessment,
)
from marketpulse.models import Trade
from marketpulse.persistence.sqlite import TradeRepository

Builder = Callable[[str, datetime, datetime, Iterable[Trade], list[Candle], bool], Evaluation]


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def stable_id(profile: str, symbol: str, start: datetime, end: datetime) -> str:
    return hashlib.sha256(f"{profile}|{symbol}|{stamp(start)}|{stamp(end)}".encode()).hexdigest()


class AnalyticsRepository(TradeRepository):
    """Share the Phase 1 thread/connection lifecycle without changing raw query behavior."""

    async def register(self, config: AnalyticsConfig) -> None:
        def write() -> None:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO analytics_profiles(profile_id,config_json) VALUES (?,?) "
                    "ON CONFLICT(profile_id) DO NOTHING",
                    (config.profile_id, config.model_dump_json()),
                )

        await self._run(write)

    async def high_sequence(self) -> int:
        return await self._run(
            lambda: self.connection.execute(
                "SELECT COALESCE(MAX(seq),0) FROM trade_changes"
            ).fetchone()[0]
        )

    async def stage_page(
        self, config: AnalyticsConfig, target: int, page_size: int
    ) -> tuple[int, int]:
        """Stage one bounded insertion-order page and its cursor in the same transaction."""

        def stage() -> tuple[int, int]:
            db = self.connection
            db.execute("BEGIN IMMEDIATE")
            try:
                cursor = db.execute(
                    "SELECT cursor FROM analytics_profiles WHERE profile_id=?", (config.profile_id,)
                ).fetchone()[0]
                rows = db.execute(
                    "SELECT * FROM trade_changes WHERE seq>? AND seq<=? ORDER BY seq LIMIT ?",
                    (cursor, target, page_size),
                ).fetchall()
                for row in rows:
                    state = db.execute(
                        "SELECT finalized_end FROM analytics_symbol_state "
                        "WHERE profile_id=? AND symbol=?",
                        (config.profile_id, row["symbol"]),
                    ).fetchone()
                    if state and state[0] and row["timestamp"] < state[0]:
                        db.execute(
                            "INSERT INTO analytics_late_trades VALUES (?,?,?,?,?)",
                            (
                                config.profile_id,
                                row["seq"],
                                row["symbol"],
                                row["timestamp"],
                                state[0],
                            ),
                        )
                    else:
                        start = window_start(
                            datetime.fromisoformat(row["timestamp"]), config.window_seconds
                        )
                        db.execute(
                            "INSERT INTO analytics_pending VALUES (?,?,?,?,?,?,?)",
                            (
                                config.profile_id,
                                row["seq"],
                                row["exchange"],
                                row["symbol"],
                                row["trade_id"],
                                row["timestamp"],
                                stamp(start),
                            ),
                        )
                    db.execute(
                        "INSERT INTO analytics_symbol_state(profile_id,symbol,max_event) "
                        "VALUES (?,?,?) ON CONFLICT(profile_id,symbol) DO UPDATE "
                        "SET max_event=MAX(max_event,excluded.max_event)",
                        (config.profile_id, row["symbol"], row["timestamp"]),
                    )
                next_cursor = rows[-1]["seq"] if rows else max(cursor, target)
                db.execute(
                    "UPDATE analytics_profiles SET cursor=? WHERE profile_id=?",
                    (next_cursor, config.profile_id),
                )
                db.commit()
                return len(rows), next_cursor
            except BaseException:
                db.rollback()
                raise

        return await self._run(stage)

    async def finalize_next(self, config: AnalyticsConfig, build: Builder) -> bool:
        """Atomically save one window, four results, optional alert, and finalization cursor."""

        def finalize() -> bool:
            db = self.connection
            # WAL read snapshot: aggregation must not hold the ingestion write lock.
            db.execute("BEGIN")
            try:
                checkpoint = db.execute(
                    "SELECT cursor FROM analytics_profiles WHERE profile_id=?", (config.profile_id,)
                ).fetchone()[0]
                states = db.execute(
                    "SELECT * FROM analytics_symbol_state WHERE profile_id=? ORDER BY symbol",
                    (config.profile_id,),
                ).fetchall()
                for state in states:
                    pending = db.execute(
                        "SELECT window_start FROM analytics_pending "
                        "WHERE profile_id=? AND symbol=? "
                        "ORDER BY window_start LIMIT 1",
                        (config.profile_id, state["symbol"]),
                    ).fetchone()
                    if pending is None:
                        continue
                    start = datetime.fromisoformat(pending[0])
                    end = start + timedelta(seconds=config.window_seconds)
                    watermark = datetime.fromisoformat(state["max_event"]) - timedelta(
                        seconds=config.allowed_lateness_seconds
                    )
                    finalized_end = (
                        datetime.fromisoformat(state["finalized_end"])
                        if state["finalized_end"]
                        else None
                    )
                    gap = False
                    if finalized_end is not None and finalized_end < start:
                        end = min(start, window_start(watermark, config.window_seconds))
                        start = finalized_end
                        gap = True
                    if end > watermark or end <= start:
                        continue
                    prior_rows = db.execute(
                        "SELECT candle_json FROM market_windows WHERE profile_id=? AND symbol=? "
                        "AND window_start<? ORDER BY window_start DESC LIMIT ?",
                        (config.profile_id, state["symbol"], stamp(start), config.history_size),
                    ).fetchall()
                    history = [Candle.model_validate_json(row[0]) for row in reversed(prior_rows)]

                    trades = (
                        ()
                        if gap
                        else self._window_trades(config.profile_id, state["symbol"], start)
                    )
                    result = build(state["symbol"], start, end, trades, history, gap)
                    identifier = stable_id(config.profile_id, state["symbol"], start, end)
                    db.commit()
                    db.execute("BEGIN IMMEDIATE")
                    actual_cursor = db.execute(
                        "SELECT cursor FROM analytics_profiles WHERE profile_id=?",
                        (config.profile_id,),
                    ).fetchone()[0]
                    actual_end = db.execute(
                        "SELECT finalized_end FROM analytics_symbol_state "
                        "WHERE profile_id=? AND symbol=?",
                        (config.profile_id, state["symbol"]),
                    ).fetchone()[0]
                    if actual_cursor != checkpoint or actual_end != state["finalized_end"]:
                        raise RuntimeError(
                            "Concurrent analytics state changed; use one worker per profile"
                        )
                    db.execute(
                        "INSERT INTO market_windows VALUES (?,?,?,?,?,?,?,?)",
                        (
                            identifier,
                            config.profile_id,
                            state["symbol"],
                            stamp(start),
                            stamp(end),
                            result.candle.quality,
                            result.candle.model_dump_json(),
                            result.risk.model_dump_json(),
                        ),
                    )
                    db.executemany(
                        "INSERT INTO detector_results VALUES (?,?,?)",
                        [
                            (identifier, item.detector, item.model_dump_json())
                            for item in result.detectors
                        ],
                    )
                    if result.risk.is_alert:
                        event = AnomalyEvent(
                            id=identifier,
                            profile_id=config.profile_id,
                            symbol=state["symbol"],
                            window_start=start,
                            window_end=end,
                            risk=result.risk,
                        )
                        db.execute(
                            "INSERT INTO anomaly_events VALUES (?,?,?,?,?,?,?,?)",
                            (
                                identifier,
                                identifier,
                                config.profile_id,
                                state["symbol"],
                                stamp(start),
                                stamp(end),
                                result.risk.score,
                                event.model_dump_json(),
                            ),
                        )
                    if not gap:
                        db.execute(
                            "DELETE FROM analytics_pending "
                            "WHERE profile_id=? AND symbol=? AND window_start=?",
                            (config.profile_id, state["symbol"], stamp(start)),
                        )
                    db.execute(
                        "UPDATE analytics_symbol_state SET finalized_end=? "
                        "WHERE profile_id=? AND symbol=?",
                        (stamp(end), config.profile_id, state["symbol"]),
                    )
                    db.commit()
                    return True
                db.commit()
                return False
            except BaseException:
                db.rollback()
                raise

        return await self._run(finalize)

    def _window_trades(self, profile: str, symbol: str, start: datetime) -> Iterable[Trade]:
        """Stream an ordered window on the owning SQLite thread with bounded fetches."""
        cursor = self.connection.execute(
            "SELECT t.* FROM analytics_pending p JOIN trades t ON "
            "t.exchange=p.exchange AND t.symbol=p.symbol AND t.trade_id=p.trade_id "
            "WHERE p.profile_id=? AND p.symbol=? AND p.window_start=? "
            "ORDER BY p.timestamp,p.trade_id",
            (profile, symbol, stamp(start)),
        )
        while rows := cursor.fetchmany(1000):
            for row in rows:
                yield Trade.model_validate({**dict(row), "buyer_maker": bool(row["buyer_maker"])})

    async def candles(self, profile: str, limit: int, symbol: str | None = None) -> list[Candle]:
        def query() -> list[Candle]:
            sql = "SELECT candle_json FROM market_windows WHERE profile_id=?"
            params: list[str | int] = [profile]
            if symbol:
                sql += " AND symbol=?"
                params.append(symbol)
            sql += " ORDER BY window_start DESC,symbol LIMIT ?"
            return [
                Candle.model_validate_json(row[0])
                for row in self.connection.execute(sql, [*params, limit])
            ]

        self._validate_limit(limit)
        return await self._run(query)

    async def events(
        self, profile: str, limit: int, symbol: str | None = None
    ) -> list[AnomalyEvent]:
        def query() -> list[AnomalyEvent]:
            sql = "SELECT event_json FROM anomaly_events WHERE profile_id=?"
            params: list[str | int] = [profile]
            if symbol:
                sql += " AND symbol=?"
                params.append(symbol)
            sql += " ORDER BY window_start DESC,symbol LIMIT ?"
            return [
                AnomalyEvent.model_validate_json(row[0])
                for row in self.connection.execute(sql, [*params, limit])
            ]

        self._validate_limit(limit)
        return await self._run(query)

    async def summary(self, profile: str, limit: int, symbol: str | None = None) -> AnomalySummary:
        events = await self.events(profile, limit, symbol)
        counts: dict[str, int] = {}
        for event in events:
            counts[event.symbol] = counts.get(event.symbol, 0) + 1
        return AnomalySummary(
            profile_id=profile,
            sample_limit=limit,
            returned_events=len(events),
            by_symbol=counts,
            max_score=max((e.risk.score for e in events if e.risk.score is not None), default=None),
            latest_window_end=max((e.window_end for e in events), default=None),
        )

    async def latest(
        self, profile: str, symbols: tuple[str, ...], limit: int
    ) -> list[LatestAnalytics]:
        def query() -> list[LatestAnalytics]:
            answers = []
            for symbol in symbols[:limit]:
                state = self.connection.execute(
                    "SELECT * FROM analytics_symbol_state WHERE profile_id=? AND symbol=?",
                    (profile, symbol),
                ).fetchone()
                row = self.connection.execute(
                    "SELECT * FROM market_windows WHERE profile_id=? AND symbol=? "
                    "ORDER BY window_start DESC LIMIT 1",
                    (profile, symbol),
                ).fetchone()
                evaluation = None
                if row:
                    evaluation = Evaluation(
                        candle=Candle.model_validate_json(row["candle_json"]),
                        risk=RiskAssessment.model_validate_json(row["risk_json"]),
                        detectors=[
                            DetectorResult.model_validate_json(item[0])
                            for item in self.connection.execute(
                                "SELECT result_json FROM detector_results "
                                "WHERE window_id=? ORDER BY detector",
                                (row["id"],),
                            )
                        ],
                    )
                counts = [
                    self.connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE profile_id=? AND symbol=?",
                        (profile, symbol),
                    ).fetchone()[0]
                    for table in ("analytics_pending", "analytics_late_trades")
                ]
                answers.append(
                    LatestAnalytics(
                        profile_id=profile,
                        symbol=symbol,
                        status=evaluation.risk.status if evaluation else "insufficient_history",
                        max_event_time=state["max_event"] if state else None,
                        finalized_through=state["finalized_end"] if state else None,
                        pending_trades=counts[0],
                        late_trades=counts[1],
                        evaluation=evaluation,
                        explanation=evaluation.risk.explanation
                        if evaluation
                        else "No finalized eligible history. Waiting for committed event-time "
                        "progress and baseline warm-up; no alert.",
                    )
                )
            return answers

        self._validate_limit(limit)
        return await self._run(query)

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
