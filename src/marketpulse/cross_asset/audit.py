"""Read-only readiness audit; never opens the repository or runs migrations."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta

from marketpulse.config import Settings


def audit(settings: Settings) -> dict:
    path = settings.database_path.resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        profile = settings.analytics.profile_id
        symbols = []
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            raw = dict(
                db.execute(
                    "SELECT COUNT(*) trades,MIN(timestamp) first_event,MAX(timestamp) last_event "
                    "FROM trades WHERE symbol=?",
                    (symbol,),
                ).fetchone()
            )
            state = db.execute(
                "SELECT * FROM analytics_symbol_state WHERE profile_id=? AND symbol=?",
                (profile, symbol),
            ).fetchone()
            quality = dict(
                db.execute(
                    "SELECT quality,COUNT(*) FROM market_windows WHERE profile_id=? AND symbol=? "
                    "GROUP BY quality",
                    (profile, symbol),
                ).fetchall()
            )
            pending = db.execute(
                "SELECT COUNT(*),MIN(timestamp),MAX(timestamp) FROM analytics_pending "
                "WHERE profile_id=? AND symbol=?",
                (profile, symbol),
            ).fetchone()
            watermark = (
                (
                    datetime.fromisoformat(state["max_event"])
                    - timedelta(seconds=settings.analytics.allowed_lateness_seconds)
                )
                if state
                else None
            )
            symbols.append(
                {
                    "symbol": symbol,
                    **raw,
                    "state": dict(state) if state else None,
                    "quality_counts": quality,
                    "pending_trades": pending[0],
                    "pending_first": pending[1],
                    "pending_last": pending[2],
                    "watermark": watermark.isoformat() if watermark else None,
                    "late_trades": db.execute(
                        "SELECT COUNT(*) FROM analytics_late_trades "
                        "WHERE profile_id=? AND symbol=?",
                        (profile, symbol),
                    ).fetchone()[0],
                }
            )
        high = db.execute("SELECT COALESCE(MAX(seq),0) FROM trade_changes").fetchone()[0]
        row = db.execute(
            "SELECT cursor FROM analytics_profiles WHERE profile_id=?", (profile,)
        ).fetchone()
        hashes = {}
        for table, order in (
            ("trades", "exchange,symbol,trade_id"),
            ("market_windows", "id"),
            ("detector_results", "window_id,detector"),
            ("anomaly_events", "id"),
        ):
            digest = hashlib.sha256()
            count = 0
            for item in db.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                digest.update((json.dumps(tuple(item), separators=(",", ":")) + "\n").encode())
                count += 1
            hashes[table] = {"rows": count, "sha256": digest.hexdigest()}
        result = {
            "audited_at": datetime.now(UTC).isoformat(),
            "database": str(path),
            "inside_onedrive": "onedrive" in str(path).lower(),
            "schema_version": db.execute("PRAGMA user_version").fetchone()[0],
            "integrity": db.execute("PRAGMA integrity_check").fetchone()[0],
            "source_profile_id": profile,
            "source_config": settings.analytics.model_dump(),
            "ledger_high_sequence": high,
            "analytics_cursor": row[0] if row else None,
            "unstaged_trades": high - row[0] if row else high,
            "symbols": symbols,
            "content_hashes": hashes,
            "collector_connectivity": "unknown",
            "worker_process_state": "unknown",
        }
    db.close()
    return result


if __name__ == "__main__":
    print(json.dumps(audit(Settings()), indent=2))
