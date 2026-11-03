"""Bounded event-time replay and atomic append/checkpoint on the SQLite worker thread."""

import hashlib
from datetime import UTC, datetime, timedelta

from marketpulse.analytics.models import Candle
from marketpulse.config import Settings
from marketpulse.cross_asset.config import SYMBOLS
from marketpulse.cross_asset.engine import evaluate
from marketpulse.cross_asset.models import (
    BreakdownEvent,
    CrossProcessingStatus,
    CrossSnapshot,
    RelationshipMatrix,
    SourceProgress,
)
from marketpulse.persistence.analytics import AnalyticsRepository, stamp


def identity(settings: Settings) -> str:
    return settings.cross_asset.profile_id(
        settings.analytics.profile_id, settings.analytics.window_seconds
    )


class CrossAssetRepository(AnalyticsRepository):
    def _source_states(self, settings: Settings) -> list:
        return [
            self.connection.execute(
                "SELECT * FROM analytics_symbol_state WHERE profile_id=? AND symbol=?",
                (settings.analytics.profile_id, symbol),
            ).fetchone()
            for symbol in SYMBOLS
        ]

    def _safe_end(self, settings: Settings) -> datetime | None:
        states = self._source_states(settings)
        if any(row is None or row["finalized_end"] is None for row in states):
            return None
        return min(datetime.fromisoformat(row["finalized_end"]) for row in states)

    async def cross_step(self, settings: Settings) -> bool:
        """Read bounded inputs, calculate without writer lock, then CAS append atomically.

        All three source finalization boundaries must cover the output timestamp.
        No source rows may be updated/deleted under a profile (Phase 2 invariant).
        """

        def step() -> bool:
            db = self.connection
            profile = identity(settings)
            source = settings.analytics.profile_id
            seconds = settings.analytics.window_seconds
            delta = timedelta(seconds=seconds)
            with db:
                db.execute(
                    "INSERT INTO cross_profiles(profile_id,source_profile_id,config_json) "
                    "VALUES (?,?,?) ON CONFLICT(profile_id) DO NOTHING",
                    (profile, source, settings.cross_asset.model_dump_json()),
                )
            db.execute("BEGIN")
            try:
                state = db.execute(
                    "SELECT * FROM cross_profiles WHERE profile_id=?", (profile,)
                ).fetchone()
                safe = self._safe_end(settings)
                if safe is None:
                    db.commit()
                    return False
                cursor = (
                    datetime.fromisoformat(state["processed_through"])
                    if state["processed_through"]
                    else None
                )
                if cursor is not None and cursor >= safe:
                    db.commit()
                    return False
                if cursor is None:
                    # Three indexed first-row reads, once per new profile, not a global rescan.
                    first = [
                        db.execute(
                            "SELECT window_start FROM market_windows "
                            "WHERE profile_id=? AND symbol=? ORDER BY window_start LIMIT 1",
                            (source, symbol),
                        ).fetchone()
                        for symbol in SYMBOLS
                    ]
                    time = min(datetime.fromisoformat(row[0]) for row in first if row) + delta
                else:
                    time = cursor + delta
                # Compact long completely cold outages once every lookback has expired.
                lower = time - delta * (
                    settings.cross_asset.lookback + settings.cross_asset.max_lag + 1
                )
                recent = any(
                    db.execute(
                        "SELECT 1 FROM market_windows WHERE profile_id=? "
                        "AND symbol=? AND window_start>=? AND window_start<? "
                        "AND quality='observed' LIMIT 1",
                        (source, symbol, stamp(lower), stamp(time)),
                    ).fetchone()
                    for symbol in SYMBOLS
                )
                skipped = 0
                if not recent:
                    upcoming = [
                        db.execute(
                            "SELECT window_start FROM market_windows WHERE profile_id=? "
                            "AND symbol=? AND window_start>=? AND quality='observed' "
                            "ORDER BY window_start LIMIT 1",
                            (source, symbol, stamp(time)),
                        ).fetchone()
                        for symbol in SYMBOLS
                    ]
                    next_times = [datetime.fromisoformat(row[0]) + delta for row in upcoming if row]
                    advanced = min(safe, min(next_times)) if next_times else safe
                    if advanced > time:
                        skipped = int((advanced - time).total_seconds()) // seconds
                        time = advanced
                if time > safe:
                    db.commit()
                    return False
                lower = time - delta * (
                    settings.cross_asset.lookback + settings.cross_asset.max_lag + 1
                )
                candles = [
                    Candle.model_validate_json(row[0])
                    for symbol in SYMBOLS
                    for row in db.execute(
                        "SELECT candle_json FROM market_windows WHERE profile_id=? "
                        "AND symbol=? AND window_start>=? AND window_start<? ORDER BY window_start",
                        (source, symbol, stamp(lower), stamp(time)),
                    )
                ]
                prior = [
                    CrossSnapshot.model_validate_json(row[0])
                    for row in db.execute(
                        "SELECT result_json FROM cross_snapshots WHERE profile_id=? "
                        "AND window_end<? "
                        "ORDER BY window_end DESC LIMIT ?",
                        (profile, stamp(time), settings.cross_asset.baseline_windows),
                    )
                ]
                snapshot = evaluate(candles, prior, time, source, seconds, settings.cross_asset)
                snapshot = snapshot.model_copy(update={"skipped_intervals": skipped})
                db.commit()
                db.execute("BEGIN IMMEDIATE")
                changed = db.execute(
                    "UPDATE cross_profiles SET processed_through=?, "
                    "snapshot_count=snapshot_count+1,last_completed_at=? WHERE profile_id=? "
                    "AND processed_through IS ?",
                    (stamp(time), stamp(datetime.now(UTC)), profile, state["processed_through"]),
                )
                if changed.rowcount != 1:
                    raise RuntimeError(
                        "Concurrent cross-asset worker changed checkpoint; run one per profile"
                    )
                db.execute(
                    "INSERT INTO cross_snapshots VALUES (?,?,?,?)",
                    (profile, stamp(time), snapshot.id, snapshot.model_dump_json()),
                )
                for relation, signal in zip(snapshot.pairs, snapshot.breakdowns, strict=True):
                    if not signal.is_event:
                        continue
                    pair = f"{relation.asset_a}-{relation.asset_b}"
                    identifier = hashlib.sha256(f"{snapshot.id}|{pair}".encode()).hexdigest()
                    event = BreakdownEvent(
                        id=identifier,
                        profile_id=profile,
                        window_end=time,
                        relationship=relation,
                        breakdown=signal,
                    )
                    db.execute(
                        "INSERT INTO cross_breakdown_events VALUES (?,?,?,?,?)",
                        (profile, stamp(time), pair, identifier, event.model_dump_json()),
                    )
                db.commit()
                return True
            except BaseException:
                db.rollback()
                raise

        return await self._run(step)

    async def cross_history(self, settings: Settings, limit: int) -> list[CrossSnapshot]:
        self._validate_limit(limit)
        return await self._run(
            lambda: [
                CrossSnapshot.model_validate_json(row[0])
                for row in self.connection.execute(
                    "SELECT result_json FROM cross_snapshots WHERE profile_id=? "
                    "ORDER BY window_end DESC LIMIT ?",
                    (identity(settings), limit),
                )
            ]
        )

    async def cross_latest(self, settings: Settings) -> RelationshipMatrix:
        history = await self.cross_history(settings, 1)
        return RelationshipMatrix(
            profile_id=identity(settings),
            source_profile_id=settings.analytics.profile_id,
            symbols=list(SYMBOLS),
            status=history[0].status if history else "insufficient_history",
            latest=history[0] if history else None,
            explanation="Current configured policy only. No relationship is inferred without "
            "synchronized eligible completed returns and sample/coverage support.",
        )

    async def cross_events(
        self, settings: Settings, limit: int, pair: str | None = None
    ) -> list[BreakdownEvent]:
        self._validate_limit(limit)

        def query() -> list[BreakdownEvent]:
            sql = "SELECT event_json FROM cross_breakdown_events WHERE profile_id=?"
            params = [identity(settings)]
            if pair:
                sql += " AND pair=?"
                params.append(pair)
            return [
                BreakdownEvent.model_validate_json(row[0])
                for row in self.connection.execute(
                    sql + " ORDER BY window_end DESC,pair LIMIT ?", [*params, limit]
                )
            ]

        return await self._run(query)

    async def cross_status(self, settings: Settings) -> CrossProcessingStatus:
        def query() -> CrossProcessingStatus:
            db = self.connection
            # Consistent read snapshot across source/cross checkpoints.
            db.execute("BEGIN")
            try:
                row = db.execute(
                    "SELECT * FROM cross_profiles WHERE profile_id=?", (identity(settings),)
                ).fetchone()
                safe = self._safe_end(settings)
                processed = (
                    datetime.fromisoformat(row["processed_through"])
                    if row and row["processed_through"]
                    else None
                )
                remaining = (
                    max(
                        0,
                        int((safe - processed).total_seconds())
                        // settings.analytics.window_seconds,
                    )
                    if safe and processed
                    else 0
                )
                if safe and processed is None:
                    starts = [
                        db.execute(
                            "SELECT window_start FROM market_windows WHERE profile_id=? "
                            "AND symbol=? ORDER BY window_start LIMIT 1",
                            (settings.analytics.profile_id, symbol),
                        ).fetchone()
                        for symbol in SYMBOLS
                    ]
                    origin = min(datetime.fromisoformat(item[0]) for item in starts if item)
                    remaining = max(
                        0, int((safe - origin).total_seconds()) // settings.analytics.window_seconds
                    )
                sources = []
                for symbol, state in zip(SYMBOLS, self._source_states(settings), strict=True):
                    counts = [
                        db.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE profile_id=? AND symbol=?",
                            (settings.analytics.profile_id, symbol),
                        ).fetchone()[0]
                        for table in ("analytics_pending", "analytics_late_trades")
                    ]
                    sources.append(
                        SourceProgress(
                            symbol=symbol,
                            max_event_time=state["max_event"] if state else None,
                            finalized_through=state["finalized_end"] if state else None,
                            pending_trades=counts[0],
                            late_trades=counts[1],
                        )
                    )
                high = db.execute("SELECT COALESCE(MAX(seq),0) FROM trade_changes").fetchone()[0]
                source = db.execute(
                    "SELECT cursor FROM analytics_profiles WHERE profile_id=?",
                    (settings.analytics.profile_id,),
                ).fetchone()
                status = (
                    "not_started"
                    if row is None
                    else "waiting_for_sources"
                    if safe is None
                    else "catching_up"
                    if processed is None or remaining
                    else "caught_up"
                )
                result = CrossProcessingStatus(
                    profile_id=identity(settings),
                    source_profile_id=settings.analytics.profile_id,
                    state=status,
                    processed_through=processed,
                    safe_through=safe,
                    remaining_intervals=remaining,
                    snapshots=row["snapshot_count"] if row else 0,
                    last_completed_at=row["last_completed_at"] if row else None,
                    source_unstaged_trades=high - source[0] if source else high,
                    sources=sources,
                    database_inside_onedrive="onedrive"
                    in str(settings.database_path.resolve()).lower(),
                    explanation="Progress is relative to finalized source event time, "
                    "not wall-clock connectivity. Pending source trades may legitimately "
                    "await the watermark. Unknown worker heartbeat. "
                    "Remaining grid intervals can be compacted when all return history is empty.",
                )
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise

        return await self._run(query)
