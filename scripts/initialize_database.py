"""Initialize a new configured database without a server or exchange connection.

Existing databases are refused. Research schema 4 remains an explicit migration.
"""

import asyncio
from pathlib import Path

from marketpulse.config import Settings
from marketpulse.persistence.sqlite import TradeRepository


async def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve exclusively: never initialize, replace or migrate an existing database.
    with path.open("xb"):
        pass
    async with TradeRepository(path) as repository:
        await repository.ping()


def main() -> None:
    path = Settings().database_path.resolve()
    asyncio.run(initialize(path))
    print(f"Initialized new schema-3 database: {path}")
    print("Research requires the separate verified-backup/schema-4 migration.")


if __name__ == "__main__":
    main()
