"""Compare original tables with a verified backup, using read-only SQLite connections."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from marketpulse.config import Settings

TABLES = (
    "trades",
    "trade_changes",
    "analytics_profiles",
    "analytics_symbol_state",
    "analytics_pending",
    "analytics_late_trades",
    "market_windows",
    "detector_results",
    "anomaly_events",
)


def fingerprints(path: Path) -> dict:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        result = {}
        for table in TABLES:
            # Names are the fixed schema list above; ordering includes every stored column.
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
            order = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
            digest, count = hashlib.sha256(), 0
            for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                digest.update((json.dumps(row, separators=(",", ":")) + "\n").encode())
                count += 1
            result[table] = {"rows": count, "sha256": digest.hexdigest()}
        return result
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    args = parser.parse_args()
    original = fingerprints(args.baseline)
    current = fingerprints(Settings().database_path)
    print(
        json.dumps(
            {
                table: {
                    "unchanged": original[table] == current[table],
                    "rows": current[table]["rows"],
                }
                for table in TABLES
            },
            indent=2,
        )
    )
    if original != current:
        raise SystemExit(
            "Source contents differ from the baseline; check for concurrent collection."
        )


if __name__ == "__main__":
    main()
