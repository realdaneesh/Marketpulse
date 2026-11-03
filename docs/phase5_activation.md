# Controlled research activation

This is a portable operational checklist, not a record of any user's deployment.
No private database, capture, process inventory, cutover evidence or backup is
included. Research Lab becomes available after the configured database has schema 4
and a real or explicitly synthetic test experiment has been processed.

## Fresh installation

Follow the [README](../README.md) to install dependencies and create a private `.env`.
Run the one-shot initializer before any services when creating a new database:

```bash
python scripts/initialize_database.py
```

It refuses an existing file. The Phase 1?4 schema is version 3. Research migration
is deliberately explicit and is not triggered by a status request or API import.

## Existing installation: approval and shutdown

1. Inspect actual service commands, process identities, working directories,
   environment overrides and database file owners. Never act on a historical PID.
2. Confirm the selected database, production source/cross profiles, full integrity,
   schema and worker checkpoints. Preserve local evidence outside Git.
3. Obtain approval for any service interruption or schema change. Stop the collector
   gracefully, allow Phase 2 and Phase 4 to catch up to their supported event-time
   boundaries, then stop those workers and the API. Do not stop the frontend.
4. Confirm there are no remaining file owners. Pending observations that have not
   crossed their watermark remain pending; do not lower eligibility thresholds.

Do not launch duplicate workers. No generic process-killing command is supplied:
operating-system process/console handling must be checked for the actual deployment.

## Verified backup and explicit migration

Derive the real configured path and choose a fresh backup filename:

```powershell
# PowerShell; run only after the required approval and controlled shutdown.
$dbPath = python -c "from marketpulse.config import Settings; print(Settings().database_path.resolve())"
python -m marketpulse.research.cli migrate --database "$dbPath" --backup data/backups/before-research.sqlite3
```

```bash
# Bash equivalent:
dbPath="$(python -c 'from marketpulse.config import Settings; print(Settings().database_path.resolve())')"
python -m marketpulse.research.cli migrate --database "$dbPath" --backup data/backups/before-research.sqlite3
```

The backup uses SQLite's backup API, including committed WAL content, and refuses
an existing destination. Before DDL, the CLI verifies source/backup integrity and
all table counts/content hashes and refuses a changed source. Migration adds only
six research tables and indexes, transactionally changing version 3 to 4. Original
trade, analytics, detector, alert, profile and checkpoint content remains intact.
The command verifies preservation again after DDL. Keep the backup and originals.

For deployment acceptance, also retain original schema definitions and compare
production profile configuration/state explicitly before and immediately after
migration. Schema 4 has 19 tables in the current installation design, including
`sqlite_sequence`; all 13 pre-research tables must be unchanged at the stopped
migration boundary. After restart, legitimate production progress and new research
sequence entries are expected changes, not a reason to reset state.

On any failed backup, preservation, migration or restart verification: halt,
preserve the evidence/files and report the problem. Do not attempt an automatic
rollback. See [storage and rollback](database_relocation.md).

## Restart and demonstrate progress

Restart exactly the approved stopped services with the same `.env` and statistical
policies, once each. Keep the existing frontend. Recheck database handles and paths.
Compare actual committed trade counts and timestamps, Phase 2 staging/finalization,
and Phase 4 checkpoints/snapshots at two observations about 15 seconds apart.
A sparse market or minute boundary can require a longer observation for candle
finalization; do not fabricate progress from a running process or reachable API.

## One bounded experiment

Choose your own aware UTC grid-aligned range whose end is finalized for all assets.
Replace `START_UTC` and `END_UTC` with that available history:

```bash
python -m marketpulse.research.cli run --store "$dbPath" \
  --start "START_UTC" --end "END_UTC" --batch 128 --max-batches 10
```

In PowerShell use a single line or backtick continuation. This is a finite job,
not an additional watch service. Its versioned configuration, source profiles and
frozen data fingerprint determine its ID. Verify completion, replay discrepancies,
evidence and statistical readiness; retain any discrepancy rather than correcting
production output. Insufficient history is a valid result.

## API and dashboard acceptance

The API has 23 read-only GET routes: seven original, seven cross-asset and nine
versioned research routes. Verify HTTP status and model-valid JSON, directly and
through the Vite proxy. Obtain real experiment/discovery IDs from list responses
before testing detail/evidence routes; empty installations need not have detail IDs.
An absent discovery should remain absent rather than being manufactured for a check.

Open `/research` and verify the selected experiment, progress, replay differences,
coverage, chronological reliability details, actual findings and evidence. Exploratory
CUSUM changes remain exploratory even inside the calendar test segment. Unsupported
sequences must show insufficient data and null inferential quantities. Test desktop
and mobile layouts without injecting synthetic results into production requests.

Capture sanitized acceptance screenshots only with explicit permission and a clear
data provenance label. Keep local operational evidence, private paths and process
IDs out of the public repository. Record exact results rather than assuming an
older implementation test run proves a new deployment is healthy.

See [research methods](research_validation.md) and [the dashboard/API guide](dashboard.md).
