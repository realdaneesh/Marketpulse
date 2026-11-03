"""Read real finalized data into a temporary research store; never migrate the live DB."""

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from marketpulse.config import Settings
from marketpulse.research.migration import migrate
from marketpulse.research.models import ResearchConfig
from marketpulse.research.worker import prepare, step


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    settings = Settings()
    with TemporaryDirectory(prefix="marketpulse-real-replay-") as directory:
        store = Path(directory) / "research.sqlite3"
        with closing(sqlite3.connect(store)) as db:
            db.execute("PRAGMA user_version=3")
            migrate(db)
        source = settings.analytics.profile_id
        cross = settings.cross_asset.profile_id(source, settings.analytics.window_seconds)
        state = prepare(
            store, settings.database_path, source, cross, args.start, args.end, ResearchConfig()
        )
        while state.state not in ("complete", "failed"):
            state = step(store, state.id)
        if state.state != "complete":
            raise RuntimeError(state.error)
        with closing(sqlite3.connect(store)) as db:
            result = json.loads(
                db.execute("SELECT results_json FROM research_experiments").fetchone()[0]
            )
        if step(store, state.id) != state:
            raise RuntimeError("Idempotence check failed")
        print(
            json.dumps(
                dict(
                    source_path=str(settings.database_path.resolve()),
                    mode="real_source_read_only_temporary_research_store",
                    experiment=state.model_dump(mode="json"),
                    metrics=result["metrics"],
                    change_points=result["change_points"],
                    sequences=result["sequences"],
                    discoveries=result["discoveries"],
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
