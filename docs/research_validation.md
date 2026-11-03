# Advanced market discovery and research validation

Phase 5 provides reproducible historical replay, descriptive detector evaluation,
robust structural-change evidence and guarded cross-asset sequence research.
Research is isolated from production alerts. New installations initialize through
schema 3; research schema 4 is an explicit opt-in migration with a verified backup.
See the [activation checklist](phase5_activation.md).

No private capture, operational evidence or live finding is shipped. Readiness
must be evaluated from your own eligible history. Empty and insufficient-data
states are valid results. Phase 6 and predictive models are outside this scope.

## Reproducible historical replay

Experiments select a fixed UTC epoch-aligned interval `[start,end]`: candle starts
are at or after `start`, and candle ends at or before `end`. All three source
finalized boundaries must reach `end`. Limits are 10,080 grid intervals per
experiment (seven days for one-minute candles). Longer captures require separate,
explicitly identified experiments; there is no implicit rolling selection of test
periods. Compact missing rows are not expanded into fabricated candles.

Input capture opens SQLite using `mode=ro`, `query_only=ON`, and a consistent WAL
read transaction. It stores bounded source candles, detector/risk results, source
policy, cross policy and preceding context in `research_experiments.inputs_json`.
No raw-trade rescan is necessary. Context includes preceding Phase 2 history,
cross-return lookback/lag closes, and preceding cross baseline snapshots.

The source configuration's original JSON is retained alongside its parsed form:
Phase 2 contribution/explanation order depends on the original weight mapping's
insertion order. Canonicalizing that mapping before replay would create false
textual discrepancies. Production scoring is unchanged.

`SHA256(canonical(inputs))` fingerprints all frozen evidence. Research profile
identity hashes configuration and source/cross profile IDs. Experiment identity
hashes that profile and fingerprint. Operational creation/completion clocks are
excluded from deterministic analysis results. Identical evidence/configuration
gives the same experiment ID and results, independent of batch size or restart.

Replay calls the existing Phase 2 detector/scoring functions and Phase 4 engine,
with strictly preceding context. Full results, including explanations, are compared.
Phase 4 `skipped_intervals` is copied as worker scheduling metadata rather than
claimed as a statistical rederivation. Differences are persisted per evaluation
and counted per mismatching evaluation; production outputs are never corrected.
This is **single-step observational replay using persisted preceding context**,
not independent re-ingestion, an independent statistical implementation, or proof
that the original detectors are scientifically valid.

## Detector evaluation and observation quality

Volume, volatility, imbalance, price shock and correlation breakdown are summarized
by entity and chronological segment. Outputs include ready evaluations, flags,
nullable flag frequency, warm-up exclusions, other coverage/activity exclusions,
expected grid slots, eligible coverage, episode counts, observed episode durations,
score histograms and same-asset detector overlaps. Histogram bins have width five,
with the final bin including score 100.

```text
flag_frequency = flagged_ready_evaluations / ready_evaluations
eligible_coverage = ready_evaluations / expected_segment_grid_slots
```

Zero denominators give null frequency. Missing slots, including compact outages
without a separately persisted research evaluation, remain in coverage denominators.
Consecutive flags form an episode only when timestamps are exactly one candle
interval apart. Unavailable samples, gaps and segment changes break grouping.
Durations are observed flagged-window durations; boundary episodes can be censored
and are not guaranteed complete real-world event lifetimes. Overlap is co-occurrence,
not independent corroboration. Counts of overlapping rolling evaluations are not
effective independent sample sizes.

There are no defensible external event labels. Alert frequency is **not** a
false-positive rate. Precision, recall, F1 and accuracy are deliberately absent.
Statistical rarity alone cannot certify a meaningful real-world event.

## Robust structural-change method

Four feature families are monitored: log positive quote volume, within-candle
realized volatility, signed aggressive imbalance and ready pairwise correlation.
Observed source quality is required; imbalance retains the source activity gate,
and correlation retains Phase 4's sample/current-eligibility/coverage gates.
There is no price fill, gap bridging, or substitution of unavailable values.

Each stream initializes from 30 preceding contiguous eligible observations. The
baseline is frozen until a flag or reset; the current evaluated observation is
never used to initialize its own baseline.

```text
m = median(initialization observations)
s = max(1.4826 * median(abs(x - m)), feature_floor)
z_t = clip((x_t - m) / s, -8, 8)
Cplus_t  = max(0, Cplus_previous  + z_t - 0.5)
Cminus_t = max(0, Cminus_previous - z_t - 0.5)
```

Floors are 0.05 log-volume units, 0.000001 volatility units, 0.01 imbalance
units, and 0.05 correlation units. A flag requires the appropriate cumulative
score ≥8, three consecutive same-direction observations, and the recent median's
absolute shift ≥1.5 baseline scales. Floors, clipping and persistent effect gates
limit degenerate-scale/heavy-tail behavior; they do not calibrate significance.
Initialization, allowance, threshold, clipping, effect and persistence settings
are part of versioned configuration; feature floors are fixed `research-v1` policy.

Missing/ineligible values, nonadjacent times, fold changes and embargo windows
reset the stream. A flag resets and reinitializes it to avoid repeated flags from
one unchecked excursion. Flags expose baseline, scale, signed effect, accumulated
score, threshold, direction, actual number of observations consumed, and source
references. The reported start is the first of the persistence-gate observations;
it is not an estimated economic structural-break onset or baseline start.

Comparison with production events asks whether a flag occurred in the preceding
configured lag window, including the current timestamp. It uses no later alerts.
Proximity is descriptive; neither method's flags are treated as labels for the other.

Predeclared sensitivity counts compare primary development folds, initialization
length +15, threshold ×1.25, and excluding the first five observations after gaps.
Test data cannot tune these variants. `primary` separately counts the complete
experiment; compare variants with `primary_development`, not the all-fold total.
None of these gap policies fills missing data.

## Chronological design and event-sequence research

Calendar grid slots are divided 60% train / 20% validation / 20% test, using floor
indices. The beginning of each later fold is embargoed by

```text
E = max(source_history_size + 1,
        cross_lookback + cross_baseline_windows + cross_max_lag + 2)
```

The default source/cross policies yield E=125 intervals. Embargo can consume an
entire small fold: such a fold is unavailable, not shortened to obtain results.
CUSUM also starts fresh within each fold. Production detectors continue to use
their original preceding histories; the purge separates the observations that
enter development and held-out research summaries. No random train/test shuffling
or automatic threshold tuning is used.

The six ordered asset hypotheses are fixed before testing. The event process is
the union of the four ready Phase 2 detector flags for each asset; **all four must
be ready** for an interval to count as eligible sequence exposure. An episode
starts with the first flag following an eligible unflagged interval. Its knowledge
time is that candle's finalized end. Episodes already active at a block boundary
are left-censored and do not create an onset.

`A precedes B within k` means an A onset at t followed by a B onset in `(t,t+kΔ]`.
The default fixed k=3 aggregates positive lags one through three; it does not select
the best lag after inspecting outcomes. Simultaneous onsets at t are counted
separately. All required intervals must be jointly eligible, contiguous, and in
the same fold. Greedy chronological exposure windows do not overlap; a follower
onset cannot be reused in two ordered opportunities within one pair's analysis.
Controls are nonoverlapping eligible windows with no active leader throughout
their exposure. A constant active event is never interpreted as repeated onsets.

```text
conditional_rate = opportunities followed by a follower onset / leader opportunities
baseline_rate = control windows with a follower onset / control windows
effect = conditional_rate - baseline_rate
lift = conditional_rate / baseline_rate
```

Lift is null when the baseline rate is zero. Descriptive counts/rates may be shown
under insufficient support; no inferential interval or p-value is then shown.
The control baseline is explicitly conditional on absence of leader activity,
not an unconditional market event rate.

## Dependence, uncertainty and multiplicity

Jointly eligible runs are partitioned into disjoint blocks of length
`max(configured_block_length, source_history_size+1, 2*k+3)`, normally 120.
Short tails and incomplete blocks are omitted, and coverage uses **all expected
fold slots**, not only surviving data. Point estimates and uncertainty calculations
use this same block population. At least eight blocks, ten leader episodes, ten
follower episodes, ten leader opportunities, thirty controls and 80% block coverage
are required. The field `blocks` does not assert that disjoint blocks are independent.

A fixed-seed (1729), 199-replicate joint-block bootstrap resamples sufficient event
counts by block and gives a percentile interval for the rate difference. The null
permutes entire follower blocks against the leader blocks, preserving each
follower block's temporal clustering and censoring block boundaries. This tests
positive excess association under stationarity/exchangeability across blocks;
it is not a distribution-free test under arbitrary market nonstationarity.
At least 90% of requested bootstrap and null replicates must have defined effects.

```text
p_surrogate = (1 + null effects >= observed effect) / (1 + valid null replicates)
BY_adjusted_p_(i) = min over j>=i of [1, p_(j) * m * H_m / j]
H_m = sum(1/j, j=1..m), m=6 ordered pairs
```

The implementation also tests BH (`H_m=1`), but uses the more conservative BY
adjustment for the dependent pair family. Unavailable hypotheses remain in the
family as p=1 during adjustment and are returned as null. Multiplicity correction
cannot rescue invalid underlying surrogate p-values. These are assumption-dependent
research quantities, not calibrated confidence or guarantees of FDR under an
incorrect null. Eight blocks is a minimum policy gate, not proof of asymptotic validity.

Selection requires supported positive effects ≥0.1 in both training and validation.
Only a supported test result with effect ≥0.1, lower bootstrap bound >0 and
BY-adjusted surrogate p≤0.05 receives `held_out_association`. All six test hypotheses
remain in the correction family. This label denotes an internal, assumption-dependent
association check, not independent external replication or profitable prediction.
With 199 resamples, the smallest surrogate p-value is 0.005; BY further limits
resolution and power for six hypotheses. A supported effect can remain unconfirmed.
Resample changes must be predeclared, never chosen after inspecting test results.

Repeated experiments, alternative universes and manual searches create additional
multiplicity not controlled by the six-pair correction.

## Findings and evidence

CUSUM flags generate explicitly exploratory discovery records. Supported held-out
sequence results can generate separately labeled association records. Stable IDs,
assets, evidence UTC range, observation support, baseline, signed effect, readiness,
coverage, method/configuration version, evidence references, explanations and
limitations accompany every discovery. CUSUM support coverage refers to its required
contiguous eligible observations, not exchange-certified capture coverage.

The discovery evidence endpoint returns referenced frozen candle, cross snapshot
and change-point objects. A sequence discovery references the experiment's named
ordered-pair/test sequence result; detailed sequence metrics are available through
the experiment sequence endpoint. Full frozen baseline context remains in the
experiment input bundle rather than duplicating all source rows in every card.

## Storage, migration and processing

Research schema 4 adds only six tables: `research_experiments`,
`research_evaluations`, `research_metrics`, `research_change_points`,
`research_sequences`, and `research_discoveries`. Research profile identity,
configuration, fingerprint, frozen inputs, failure/readiness state and durable
cursor belong to the experiment. Indexes support per-experiment event reads.
No existing trade, candle, alert, profile or production checkpoint is rewritten.

The base migration accepts version 4 but still installs only through version 3.
Research migration is an explicit command: importing the updated factory or starting
the updated API does **not** install it. Unknown versions above 4 fail visibly.
Research DDL and version changes are transactional and idempotent. Failure tests
prove rollback and preservation of original table counts/content hashes.

Do not run a live migration without explicit approval. The intended cutover is:

1. Recheck current process identities and obtain approval for necessary interruption.
2. Gracefully stop the collector, allow Phase 2 and Phase 4 to catch up, then stop
   those workers and API. Preserve the frontend. Do not force termination.
3. Run the command below with a **fresh, non-existing** backup path. It uses SQLite's
   backup API (including committed WAL), integrity checks, and all-table count/hash
   comparison. Concurrent source changes cause a halt before DDL. After DDL it
   checks every original table again. Preserve both files on any failure.
4. Restart only approved stopped services with the existing `.env` and policies.
   Recheck handles, live commits, both worker checkpoints, and all 23 API routes.
5. Run a bounded research experiment only after approved activation.

```powershell
# AFTER explicit approval and controlled service shutdown only:
$activeDb = python -c "from marketpulse.config import Settings; print(Settings().database_path.resolve())"
$backupStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDb = Join-Path (Get-Location) ('data/phase5-before-' + $backupStamp + '.sqlite3')
.\.venv\Scripts\python.exe -m marketpulse.research.cli migrate --database $activeDb --backup $backupDb
```

Existing rollback snapshots are never migration targets. Do not simply
switch back to a frozen old database and lose newer observations. Follow the
[controlled relocation/rollback guide](database_relocation.md), preserving the
newest database first. Do not manually decrement schema versions or drop tables.

Each worker pass performs at most 128 replay evaluations (configurable 1–512), then
atomically commits rows and cursor under compare-and-swap protection. Competing
workers fail visibly. Exceptions retain committed progress and record failure;
failed experiments are not silently retried or corrected. Ctrl+C preserves the last
committed batch. Repeating the same run resumes an unfinished job and reuses a
completed job without changing completion time or duplicating events.

The source is captured once per preparation, not rescanned on polling. A batch
loads the bounded frozen bundle, verifies its fingerprint, and uses indexed in-memory
timestamps/lazy models for preceding history. Final summaries are calculated from
the bounded experiment outside the SQLite write transaction, then committed
atomically with events and completion state. This is a finite batch research worker,
not a new always-on watch process or unlimited-memory streaming system. The seven-day
cap bounds memory; large permitted jobs can still consume substantial memory and
CPU. No retention or multi-month stress-throughput claim is made.

```powershell
# AFTER schema activation. Start/end must be finalized aware UTC grid boundaries.
.\.venv\Scripts\python.exe -m marketpulse.research.cli run `
  --store $activeDb `
  --start START_UTC --end END_UTC `
  --batch 128 --max-batches 10
```

Source defaults to actual `Settings().database_path`; `--source`, `--source-profile`,
`--cross-profile` and a JSON `--config` allow explicit research selection. The store
must already exist at schema 4. Operational batch size does not change experiment
identity. The API and research store must select the same database to display results.

Real-data verification can instead use a temporary isolated store, with no active
schema change or retained production research rows:

```powershell
.\.venv\Scripts\python.exe -m marketpulse.research.verify_real `
  --start START_UTC --end END_UTC
```

## Read-only API and Research Lab

Nine GET routes are added under `/api/research/v1`:

| Route | Response |
| --- | --- |
| `/status` | Schema/readiness, experiment count/latest, unknown worker connectivity |
| `/experiments` | Newest-first experiment metadata |
| `/experiments/{id}` | Configuration, fingerprint, durable progress/failure, sensitivity |
| `/experiments/{id}/metrics` | Detector/entity/segment summaries |
| `/experiments/{id}/change-points` | Explainable structural-change evidence |
| `/experiments/{id}/sequences` | Six ordered pair analyses across the three folds |
| `/experiments/{id}/discoveries` | Exploratory or held-out association records |
| `/discoveries/{id}` | Discovery detail |
| `/discoveries/{id}/evidence` | Referenced frozen evidence objects |

IDs must be 64 lowercase hex characters. Lists validate limit 1–200 (default100)
and offset 0–100,000, in deterministic stored order. Immutable experiment result
pages are stable; newest-first experiment pagination can shift if new jobs are
inserted between requests. Unknown IDs return404; invalid parameters422; unavailable
database/schema503. Status still returns200 with `schema_not_migrated` on schema3.
Models reject nonfinite values; source UTC timestamps remain aware and unavailable
statistics stay null. No request starts a job, collects trades or migrates a database.

Research Lab (`/research`) reuses the existing dark design, TanStack polling and
generated OpenAPI contracts. It offers experiment selection, progress/discrepancy
KPIs, reliability/configuration details, fold comparison tables, score/overlap and
episode summaries, CUSUM timeline, ordered-pair sequence explorer, discovery cards
and expandable evidence. Migration, empty, loading, failed/cached-data and
insufficient-support states remain explicit. Views fetch the latest100 experiments
and first200 result records per section; these are bounded views, not a complete
historical export. Production code never imports synthetic fixtures.

The API was restarted during approved activation and now serves all23 routes.
The unchanged Vite proxy targets8000; the frontend process was retained. A fresh
schema3 installation still returns the documented migration/readiness gate until
its own explicitly approved migration.

## Reproducibility and checks

Replace `START_UTC` and `END_UTC` above with an available, finalized, UTC grid-aligned
range from your own source. A fresh empty database cannot reproduce private
operational discoveries, and no such capture is required for the test suite.

The suite covers replay agreement/discrepancy retention, source preservation,
batching/restart/idempotence, policy serialization, future-data exclusion, embargoes,
holdout isolation, CUSUM initialization/reset, episodes/simultaneity, support and
missing-run gates, deterministic resampling, BH/BY, atomic failure, migration
rollback and API contracts. Frontend fixtures are actual FastAPI serializations of
explicitly synthetic temporary data; production components do not import them.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe frontend/scripts/export_openapi.py --check
.\.venv\Scripts\python.exe frontend/scripts/export_test_fixtures.py --check
.\.venv\Scripts\python.exe frontend/scripts/export_cross_fixtures.py --check
.\.venv\Scripts\python.exe frontend/scripts/export_research_fixtures.py --check
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
.\.venv\Scripts\python.exe frontend/scripts/research_browser_check.py
```

After intentional contract changes, export without `--check`, regenerate the
TypeScript schema with `npm --prefix frontend run api:generate`, and review all
fixture changes. The isolated Chrome helper uses temporary synthetic data and its
own ports; it leaves existing services and databases untouched.

See [publication readiness](github_readiness.md) for recorded verification.

## Data readiness and limitations

Short continuous spans, historical gaps, sparse episodes and overlapping windows
can make sequence inference unsupported. Keep intervals/p-values null and label
findings insufficient when support or assumptions fail. CUSUM events remain
exploratory even when their timestamp falls in a calendar test segment. An
observational replay match validates software consistency, not scientific validity.
No result is fabricated to populate the dashboard.

Research validity still requires independent event labeling where meaningful,
external chronological replication, null calibration under nonstationarity,
block-length/effective-sample analysis, coverage-selection bias assessment,
multiple-experiment correction, robustness to outliers and temporal aggregation,
and evaluation outside this three-asset universe. Pearson correlation remains
linear and outlier-sensitive. Offline replay equivalence is a software consistency
check, not evidence of predictive skill. Neither heuristic changes nor assumption-
dependent associations imply investment value, causal transmission, contagion,
crash probabilities or calibrated confidence. No public deployment is included.

## Method references

- [NIST CUSUM overview](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm).
  This implementation uses an explicitly documented robust variant, not NIST ARL calibration.
- [Benjamini and Yekutieli, dependency and false discovery control](https://www.math.tau.ac.il/~ybenja/depApr27.pdf).
  Correction presupposes valid individual hypothesis quantities; it cannot validate a misspecified null.
- [Politis and Romano, dependent-data bootstrap research](https://users.ssc.wisc.edu/~behansen/718/Politis%20Romano.pdf).
  The implemented procedure uses disjoint fixed blocks, not the stationary-bootstrap algorithm.
