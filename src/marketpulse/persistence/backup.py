"""Copy a consistent SQLite snapshot without replacing or deleting either user's database."""

import argparse
import sqlite3
from pathlib import Path

from marketpulse.config import Settings


def backup_database(source: Path, destination: Path) -> None:
    """Create a new backup, including committed WAL content; refuse existing destinations."""
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination:
        raise ValueError("source and destination must differ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation reserves this name without ever overwriting an existing file.
    with destination.open("xb"):
        pass
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(destination) as target:
                original.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("backup integrity check failed")
    finally:
        # sqlite3 context managers commit/rollback but do not close connections.
        if "target" in locals():
            target.close()
        if "original" in locals():
            original.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up MarketPulse to a new local SQLite file")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=None)
    args = parser.parse_args()
    source = args.source or Settings().database_path
    backup_database(source, args.destination)
    print(f"Backup verified: {args.destination.resolve()}")
    print("Original database preserved. Update MARKETPULSE_DATABASE_PATH for every process.")


if __name__ == "__main__":
    main()
