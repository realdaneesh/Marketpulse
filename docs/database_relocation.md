# Database storage, backup and relocation

MarketPulse uses one configured SQLite database shared by the collector, Phase 2,
Phase 4, API and finite research jobs. Set `MARKETPULSE_DATABASE_PATH` in a private
project-root `.env`; run all backend commands from that root. Process environment
variables override the file. No machine-specific database path is required or shipped.

## Storage choice

The development default is `data/marketpulse.sqlite3`. For sustained collection,
choose an absolute path on your own local, unsynchronized disk. Avoid OneDrive,
other cloud synchronization folders, network shares and removable storage while
SQLite is active. On Windows, a directory beneath `$env:LOCALAPPDATA` is one option;
set its resolved path explicitly in `.env` rather than assuming shell-variable
expansion inside dotenv values. Existing databases must not be silently relocated.

Inspect configuration without opening the database:

```bash
python -c "from marketpulse.config import Settings; print(Settings().database_path.resolve())"
```

## Consistent backup

Use SQLite's backup API so committed WAL transactions are included. Do not copy
only an open main database file and assume it contains all committed data.
Choose a new destination; the command refuses to overwrite an existing backup:

```bash
python -m marketpulse.persistence.backup --destination data/backups/manual-backup.sqlite3
```

The source defaults to the actual configured database. An explicit `--source`
selects a different existing file. The command performs an integrity check on the
backup; it does not change runtime configuration or delete the original.
For a frozen migration/relocation comparison, gracefully stop the relevant writers
and readers with the owner's approval before calculating content manifests.

## Controlled relocation

1. Identify actual database-owning processes, command lines, selected paths and
   policy profiles. A process being present does not prove a functioning pipeline.
2. Obtain approval before stopping existing services. Stop collection gracefully,
   allow analytics to consume the final committed ledger, then stop Phase 2,
   Phase 4 and the API. The frontend can remain running.
3. Confirm all file owners have exited. Keep pending trades governed by their
   event-time watermark; do not force finalization using wall time.
4. Back up the stopped source to a fresh destination with the SQLite backup API.
   Verify integrity, schema, original schema definitions, every table's count and
   deterministic content hash, profiles and checkpoints. Halt on any discrepancy.
5. Update only the supported `MARKETPULSE_DATABASE_PATH` entry in `.env`. Ensure
   any process environment override agrees. Recheck the resolved setting.
6. Restart only the stopped services, once each, after approval. Confirm their
   database handles point to the destination. Compare committed trades and worker
   checkpoints at two event-time observations; exercise API and dashboard reads.
7. Keep the original as a frozen rollback copy and retain backup/preservation
   records privately. Do not commit them to Git.

Collection pauses create unknown intervals. Accepted/persisted data can be
preserved while exchange trades during the offline period are not received or
backfilled. Eligibility and coverage reporting must reflect those gaps.

## Rollback without losing newer data

Never switch running services between two databases. A frozen pre-change copy does
not contain later trades. Obtain approval for a controlled stop, preserve the
newest database with a verified non-overwriting backup to a fresh restore path,
compare integrity/schema/content/profiles/checkpoints, then select that verified
path consistently for every service. Keep both earlier files. Halt if any check
fails; do not automatically restore an older snapshot, decrement a schema version,
truncate data or reset checkpoints.

See the [research activation checklist](phase5_activation.md) for the explicit
schema-4 migration, which is separate from a location change. Local deployment
records and operator-specific process IDs are intentionally excluded from this repository.
