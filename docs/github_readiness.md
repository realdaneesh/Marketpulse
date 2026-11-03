# GitHub publishing readiness

This repository contains Phase 1–5 source, frontend, tests, migrations, portable
documentation, generated OpenAPI contracts and explicitly synthetic test fixtures.
It intentionally excludes private configuration, local observations, database files,
cutover evidence, backups, dependency directories and build/test output.

## Git state and audit boundaries

At preparation time, this directory did not contain Git metadata. There was no
branch, remote, index, tracked file set or commit history to inspect. That initial
preparation did not initialize, stage, commit or push the project, and no existing
history was rewritten.
An isolated temporary Git directory applied the actual ignore rules to enumerate
the exact first-staging candidates; it was not the project's Git index.

The original operational documents contained personal paths and machine-specific
deployment records. Their complete originals were retained privately under ignored
`data/` storage. Public versions retain the statistical methods and replace local
cutover records with portable procedures. Neither live databases nor preserved
backups were deleted, relocated or included. Existing services were not restarted.

## Re-run the publication audit

```bash
python scripts/audit_publication.py --output data/publication-audit.json
```

The audit enumerates candidate files with Git's ignore semantics, also includes
already tracked files if Git is later initialized, checks private/generated paths,
files above 5 MiB, absolute personal paths, known token/private-key patterns and
potential credential assignments. When actual history exists, it examines reachable
blob/commit/tag objects and flags private or oversized historical artifacts. Values
are never printed in findings, only relative file/object locations and finding types.
Lockfiles and intentional synthetic fixture/contract files remain publishable.

The check is a conservative pattern scan plus manual review, not a proof that
arbitrary secret formats cannot exist. Review new changes before each publish.
If credentials are found, revoke/rotate them first and remove them from candidates.
Removing a file or adding an ignore rule does not erase existing commits. Any
history rewrite requires separate explicit approval; none was needed or performed here.

For a clean first-staging export, choose a new directory beneath ignored `data/`:

```bash
python scripts/audit_publication.py --output data/publication-audit.json \
  --export data/publication-export
```

The command refuses findings and an existing export destination. The export contains
only the reviewed candidates and excludes the private `.env`, private databases and
original machine-specific documents. This allows setup to be tested independently
of the working installation. No actual staging, commit or push occurs.

## Reproducibility checks

Use the [README](../README.md) setup commands in a clean export with new virtual and
frontend environments. Copy only the safe environment examples. The one-shot
initializer must create an empty schema-3 database and refuse an existing one.
The explicit migration must create a fresh backup, preserve original contents and
install schema 4. Empty API/list/readiness states are expected without market data.

Run backend tests/Ruff, TypeScript/ESLint/Vitest/build and all OpenAPI/fixture checks.
The optional Chrome helper uses synthetic temporary data and isolated ports; it
never needs a user's capture or collector. Screenshots in `docs/images/` are reviewed
synthetic demonstrations; live/operational browser outputs stay ignored.

The final measured results and candidate manifest are retained locally in ignored
audit artifacts. See the preparation report provided with the changes for exact
counts and any installation/network limits; do not infer a successful fresh install
from the presence of a pre-existing development environment.

## Verified preparation results

Verification environment: Windows, Python 3.14 and Node.js 24. Other operating
systems and Python versions have not been independently exercised in this preparation.
Because no Git repository/commit existed during preparation, a reviewed candidate export was
used as the fresh-clone equivalent; no private working-tree files were copied.

| Check | Measured result |
| --- | --- |
| Publishing candidates | 144 files; approximately 1.66 MB total |
| Candidate secret/path/artifact scan | No findings; no file exceeded 5 MiB |
| Git history | None existed; zero commits/tracked files/remotes, so history audit was not applicable |
| Fresh backend setup | New virtual environment; pinned requirements and documented editable install succeeded |
| Fresh frontend setup | Separate `npm ci` from committed lockfile succeeded |
| Backend tests in clean export | **170 passed, 0 failed** |
| Frontend tests in clean export | **44 passed, 0 failed**, six files |
| TypeScript / ESLint / production build | Passed in clean export |
| Ruff lint / formatting | Passed in clean export |
| OpenAPI and three fixture checks | All matched in clean export |
| Chrome desktop/mobile | **12 passed, 0 failed** using temporary synthetic data on isolated ports |
| Empty-database setup | New schema 3, existing-file refusal, verified backup and schema 4 migration passed |
| Empty API acceptance | All 23 route behaviors checked; 16 HTTP 200 responses and seven expected HTTP 404 detail responses for absent IDs |
| Documentation | Local file links resolved; two synthetic screenshots visually/metadata reviewed |
| Existing installation | Original four services and frontend identities retained; no stop/restart or live database migration |

The largest candidate is an intentional serialized synthetic fixture, approximately
391 KB. Generated contracts and lockfiles are retained; caches, environments,
bundles, screenshots outside the reviewed documentation copies, databases and local
evidence are excluded by the actual Git ignore rules.

Initial isolated test attempts encountered shared Windows temporary-directory
permissions and then a missing temporary parent. A fresh workspace-local test path
with its parent created resolved those setup issues; the complete final run passed
170 tests. The initial installer harness also disabled build isolation before its
build backend existed; the documented standard editable install succeeded. These
were setup-harness corrections, not changes to market analytics or statistical policy.

The complete relative-path candidate manifest and detailed audit JSON are retained
locally under ignored `data/` for review. The reusable audit prints locations and
finding types, never candidate secret values. This preparation does not assert
GitHub repository-name availability or grant permission to commit/push.

## Publishing decisions

Recommended repository name: **marketpulse**.

Recommended description:
> Explainable cryptocurrency anomaly intelligence, cross-asset analytics and reproducible research dashboards built with Python, FastAPI and React.

Suggested topics: `cryptocurrency`, `market-data`, `anomaly-detection`, `cross-asset`,
`quantitative-research`, `fastapi`, `react`, `typescript`, `sqlite`, `data-visualization`.
The maintainer subsequently supplied the publication target:
[realdaneesh/Marketpulse](https://github.com/realdaneesh/Marketpulse). Initial
publication targets `main` and must stop if remote history already exists. The
preparation measurements above predate Git initialization; consult the repository
branch and commit history for current publication state.

The contributors should approve licensing terms before a license is added. No
license or contributor contact/username was invented. After reviewing the complete
candidate list, separately authorize local Git initialization/staging/commit and
remote creation/push as appropriate. Nothing is published by the audit tools.
