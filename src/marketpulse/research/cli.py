"""Explicit migrations and finite research jobs. No production process control."""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from marketpulse.config import Settings
from marketpulse.persistence.backup import backup_database
from marketpulse.research.migration import migrate
from marketpulse.research.models import ResearchConfig, canonical
from marketpulse.research.worker import prepare, step


def manifest(path: Path) -> dict:
    """Stream full table contents in deterministic SQLite row order; include committed WAL."""
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        db.execute("BEGIN")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("Integrity check failed")
        tables = [
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ]
        result = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = len(db.execute(f"PRAGMA table_info({quoted})").fetchall())
            order = ",".join(str(i) for i in range(1, columns + 1))
            digest, count = hashlib.sha256(), 0
            for row in db.execute(f"SELECT * FROM {quoted} ORDER BY {order}"):
                digest.update((canonical(row) + "\n").encode())
                count += 1
            result[table] = (count, digest.hexdigest())
        return result
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    migration = sub.add_parser(
        "migrate", help="Approval required before use on the active database"
    )
    migration.add_argument("--database", type=Path, required=True)
    migration.add_argument("--backup", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--store", type=Path, required=True)
    run.add_argument("--source", type=Path)
    run.add_argument("--source-profile")
    run.add_argument("--cross-profile")
    run.add_argument("--start", type=datetime.fromisoformat, required=True)
    run.add_argument("--end", type=datetime.fromisoformat, required=True)
    run.add_argument("--config", type=Path)
    run.add_argument("--batch", type=int, default=128)
    run.add_argument("--max-batches", type=int, default=100000)
    args = parser.parse_args()
    if args.command == "migrate":
        before = manifest(args.database)
        backup_database(args.database, args.backup)
        if before != manifest(args.backup) or before != manifest(args.database):
            raise RuntimeError("Backup/source mismatch or concurrent writes; HALT before migration")
        db = sqlite3.connect(args.database, timeout=10)
        try:
            migrate(db)
        finally:
            db.close()
        after = manifest(args.database)
        # sqlite_sequence acquires a new entry only when experiments are later inserted.
        if any(after.get(table) != value for table, value in before.items()):
            raise RuntimeError("Preservation check failed; HALT, preserve both databases")
        print("Schema 4 installed; all original table counts and hashes preserved; backup verified")
        return
    if args.max_batches < 1:
        parser.error("max-batches must be positive")
    settings = Settings()
    config = (
        ResearchConfig.model_validate_json(args.config.read_text())
        if args.config
        else ResearchConfig()
    )
    source = args.source_profile or settings.analytics.profile_id
    cross = args.cross_profile or settings.cross_asset.profile_id(
        source, settings.analytics.window_seconds
    )
    state = prepare(
        args.store,
        args.source or settings.database_path,
        source,
        cross,
        args.start,
        args.end,
        config,
    )
    for _ in range(args.max_batches):
        if state.state in ("complete", "failed"):
            break
        state = step(args.store, state.id, args.batch)
    print(json.dumps(state.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
