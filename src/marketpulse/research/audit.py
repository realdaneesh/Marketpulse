"""Read-only readiness audit; no repository opening, migrations, or process control."""

import argparse
import json
import sqlite3
import time
from datetime import UTC, datetime

from marketpulse.analytics.models import Candle
from marketpulse.config import Settings


def audit() -> dict:
    settings = Settings()
    path = settings.database_path.resolve()
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        source = settings.analytics.profile_id
        profile = settings.cross_asset.profile_id(source, settings.analytics.window_seconds)
        spans = {}
        for symbol in settings.symbols:
            longest = current = eligible_returns = 0
            last = None
            qualities = {}
            for row in db.execute(
                "SELECT candle_json FROM market_windows WHERE profile_id=? "
                "AND symbol=? ORDER BY window_start",
                (source, symbol),
            ):
                c = Candle.model_validate_json(row[0])
                qualities[c.quality] = qualities.get(c.quality, 0) + max(1, c.missing_intervals)
                adjacent = last is not None and last == c.window_start
                current = (
                    current + 1
                    if c.quality == "observed" and adjacent
                    else int(c.quality == "observed")
                )
                eligible_returns += int(c.quality == "observed" and adjacent)
                longest = max(longest, current)
                last = c.window_end if c.quality == "observed" else None
            spans[symbol] = dict(
                longest_observed_candles=longest,
                latest_run=current,
                eligible_returns=eligible_returns,
                quality_intervals=qualities,
            )
        latest = db.execute(
            "SELECT result_json FROM cross_snapshots WHERE profile_id=? "
            "ORDER BY window_end DESC LIMIT 1",
            (profile,),
        ).fetchone()
        return dict(
            observed_at=datetime.now(UTC).isoformat(),
            path=str(path),
            schema=db.execute("PRAGMA user_version").fetchone()[0],
            integrity=[r[0] for r in db.execute("PRAGMA integrity_check")],
            trades=[
                dict(r)
                for r in db.execute(
                    "SELECT symbol,count(*) AS count,max(timestamp) "
                    "AS latest FROM trades GROUP BY symbol"
                )
            ],
            ledger=db.execute("SELECT max(seq) FROM trade_changes").fetchone()[0],
            source_profile=source,
            cross_profile=profile,
            cursor=db.execute(
                "SELECT cursor FROM analytics_profiles WHERE profile_id=?", (source,)
            ).fetchone()[0],
            source_states=[
                dict(r)
                for r in db.execute(
                    "SELECT * FROM analytics_symbol_state WHERE profile_id=?", (source,)
                )
            ],
            pending=db.execute(
                "SELECT count(*) FROM analytics_pending WHERE profile_id=?", (source,)
            ).fetchone()[0],
            late=db.execute(
                "SELECT count(*) FROM analytics_late_trades WHERE profile_id=?", (source,)
            ).fetchone()[0],
            anomalies=db.execute(
                "SELECT count(*) FROM anomaly_events WHERE profile_id=?", (source,)
            ).fetchone()[0],
            cross_state=dict(
                db.execute("SELECT * FROM cross_profiles WHERE profile_id=?", (profile,)).fetchone()
            ),
            spans=spans,
            latest_cross=json.loads(latest[0]) if latest else None,
        )
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.interval <= 30:
        parser.error("interval must be 0..30 seconds")
    first = audit()
    print(json.dumps(first, indent=2), flush=True)
    if args.interval:
        time.sleep(args.interval)
        print(json.dumps(audit(), indent=2))


if __name__ == "__main__":
    main()
