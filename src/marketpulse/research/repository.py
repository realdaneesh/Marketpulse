"""Read-only research access on the existing dedicated SQLite repository thread."""

import json

from marketpulse.cross_asset.repository import CrossAssetRepository
from marketpulse.research.models import Experiment, ResearchStatus


class ResearchRepository(CrossAssetRepository):
    async def research_status(self) -> ResearchStatus:
        def read():
            db = self.connection
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version < 4:
                return ResearchStatus(
                    state="schema_not_migrated",
                    schema_version=version,
                    experiments=0,
                    explanation="Research schema requires an explicitly approved migration. "
                    "Existing market services remain available.",
                )
            row = db.execute(
                "SELECT experiment_json FROM research_experiments ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            return ResearchStatus(
                state="available" if row else "not_started",
                schema_version=version,
                experiments=db.execute("SELECT count(*) FROM research_experiments").fetchone()[0],
                latest=Experiment.model_validate_json(row[0]) if row else None,
                explanation="Finite observational experiments; worker heartbeat and exchange "
                "connectivity are unknown. No labels certify event correctness.",
            )

        return await self._run(read)

    async def research_list(self, kind: str, experiment: str | None, limit: int, offset: int):
        tables = {
            "experiments": ("research_experiments", "experiment_json", "seq DESC"),
            "metrics": ("research_metrics", "result_json", "position"),
            "change-points": ("research_change_points", "result_json", "seq"),
            "sequences": ("research_sequences", "result_json", "position"),
            "discoveries": ("research_discoveries", "result_json", "seq"),
        }
        table, column, order = tables[kind]

        def read():
            where = " WHERE experiment_id=?" if experiment else ""
            params = [experiment] if experiment else []
            return [
                json.loads(r[0])
                for r in self.connection.execute(
                    f"SELECT {column} FROM {table}{where} ORDER BY {order} LIMIT ? OFFSET ?",
                    (*params, limit, offset),
                )
            ]

        return await self._run(read)

    async def research_detail(self, kind: str, key: str):
        table, column = {
            "experiments": ("research_experiments", "experiment_json"),
            "discoveries": ("research_discoveries", "result_json"),
        }[kind]

        def read():
            row = self.connection.execute(
                f"SELECT {column} FROM {table} WHERE id=?", (key,)
            ).fetchone()
            return json.loads(row[0]) if row else None

        return await self._run(read)

    async def research_evidence(self, key: str):
        def read():
            row = self.connection.execute(
                "SELECT result_json,experiment_id FROM research_discoveries WHERE id=?", (key,)
            ).fetchone()
            if row is None:
                return None
            discovery = json.loads(row[0])
            experiment = self.connection.execute(
                "SELECT inputs_json FROM research_experiments WHERE id=?", (row[1],)
            ).fetchone()
            inputs = json.loads(experiment[0])
            refs = set(discovery["evidence"])
            values = []
            for item in inputs["candles"]:
                if item["id"] in refs:
                    values.append(
                        dict(
                            id=item["id"],
                            kind="candle",
                            observation=json.loads(item["candle_json"]),
                        )
                    )
            for item in inputs["snapshots"]:
                if item["id"] in refs:
                    values.append(
                        dict(
                            id=item["id"], kind="cross", observation=json.loads(item["result_json"])
                        )
                    )
            for item in self.connection.execute(
                "SELECT id,result_json FROM research_change_points WHERE experiment_id=?", (row[1],)
            ):
                if item[0] in refs:
                    values.append(
                        dict(id=item[0], kind="change_point", observation=json.loads(item[1]))
                    )
            return values

        return await self._run(read)
