# Cross-asset market intelligence

Phase 4 studies changing relationships among BTCUSDT, ETHUSDT and SOLUSDT over
eligible completed event-time observations. It is descriptive research, not an
investment recommendation, price forecast or claim of causation. Calculations use
the Python standard library.

No market capture or private database is bundled. An empty or discontinuous source
can legitimately leave correlations, regimes and lead-lag analyses unavailable.
Inspect the read-only status endpoint or run `python -m marketpulse.cross_asset.audit`
against your own configured database. Trade times originate in Binance's validated
integer trade-time field; receipt latency, independent clock verification and
exchange-certified complete coverage are not stored.

## Eligibility and UTC alignment

The source is immutable `market_windows` under the API/worker's configured Phase 2
profile. Only `quality="observed"`, one-interval candles with positive finite closes
are eligible. Phase 2 explicitly treats these as statistically eligible while
acknowledging uncertified exchange coverage. Partial starts, data gaps, missing
ranges, wrong durations, and uncertain closes are excluded.

Grid boundaries are UTC epoch-aligned multiples of `window_seconds` (normally 60).
The return associated with a candle ending at `t` is:

```text
r_s(t) = ln(close_s(t) / close_s(t − Δ))
```

Both closes must belong to adjacent eligible source candles. Returns are
recomputed with Decimal logarithms before conversion to finite statistical floats,
so the alignment module does not trust a return without its close/quality context.
Missing values stay null; a true unchanged close produces the distinct numeric zero.
No forward fill, interpolation, or return across a missing interval is allowed.
Conflicting duplicate candles and off-grid inputs fail visibly; identical duplicates
deduplicate deterministically. Input order and timezone offsets do not change results.

The publication frontier is the **minimum finalized boundary across all three symbols**.
If any source lacks a finalized boundary, the worker waits. A faster symbol cannot
make a still-pending slower symbol appear permanently missing. Different start times
produce unavailable earlier slots, with explicit per-symbol and pairwise coverage.
Source late trades remain excluded according to Phase 2 and cannot rewrite published
cross-asset snapshots. Source modifications/deletions under an existing profile are
unsupported, as in Phase 2; use a new versioned source policy for a different replay.

## Rolling correlations and volatility

At end time `T`, the lookback consists of the latest `L` grid-end slots, inclusive
of `T`. Default `L=60`. For each pair, use only slots with both eligible returns:

```text
n = count of valid synchronized return pairs
coverage = n / L
r = Σ((x_i − mean(x)) (y_i − mean(y))) /
    sqrt(Σ(x_i − mean(x))² × Σ(y_i − mean(y))²)
```

The engine normalizes inputs before centered products for numerical stability.
It returns no coefficient when either series is constant, support is insufficient,
coverage is below policy, or either current return is ineligible. A warm-up result
is not zero correlation. Pair counts can differ; all three pairs need not use the
same missing-data mask. This pairwise-deletion matrix is not guaranteed positive
semidefinite and is not intended as a portfolio covariance matrix.

Defaults require at least 30 pairs **and** 80% of the 60 grid slots, so effective
minimum default support is 48 pairs. Current-slot eligibility prevents old numeric
correlations from being presented as current evidence during an outage. The change
field is current minus immediately preceding eligible rolling correlation; a missing
predecessor gives null. It never searches across a gap to manufacture a change.

Per-asset return volatility is the unannualized **sample standard deviation** of
eligible candle log returns in the same lookback, with the same sample/coverage and
current-slot gates. This differs from Phase 2's within-candle realized volatility.
Per-asset eligible candle count, eligible return count, expected grid count, and
return coverage are exposed separately.

## Relationship-change methodology

Each pair's baseline uses up to 60 immediately preceding contiguous ready rolling
windows, never the evaluated window or future data. An unavailable/gapped rolling
window breaks the baseline. At least 20 preceding eligible windows are required.

```text
m = median(preceding correlations)
MAD = median(abs(correlation_i − m))
scale = max(1.4826 × MAD, 0.05)
signed_change = current_correlation − m
deviation = min(100, abs(signed_change) / scale)
event = current is ready AND baseline_count >= 20
        AND deviation >= 3.5 AND abs(signed_change) >= 0.2
```

The explicit 0.05 coefficient-unit floor handles flat/zero-MAD baselines. It is a
stabilizing assumption, not an estimated standard error. All constants are configurable.
“Strengthening” means an increase in the **signed coefficient**, and “weakening” a
decrease. Thus a negative coefficient moving toward zero is increasing signed
synchronization, not a strengthening inverse relationship. Coefficients, signed
changes, median, MAD, scale, support, and the exact explanation accompany each event.

Overlapping rolling windows are strongly dependent. Counts are raw matched-return
counts, not independent effective sample sizes. Deviation scores are heuristic
evidence measures, never calibrated probabilities or significance levels. Each
qualifying timestamp/pair is an event; consecutive flags are not grouped into episodes.

## Lead–lag research and chronological holdout

All six ordered pairs are evaluated at positive lags 1 through 3 by default.
Zero lag is the ordinary relationship matrix. Opposite ordered pairs cover the
opposite timing direction. The definition is precise:

```text
A leads B by k intervals: compare r_A(t) with r_B(t + kΔ)
```

For publication at `T`, every follower target time is at or before `T` and all
sources have finalized through `T`. Candidate follower targets occupy the same
`L`-slot lookback; leading returns can begin `k` slots earlier. Both assets must
also have eligible returns at every intervening grid position, conservatively
excluding lag chains that touch a gap. Counts and coverage use the number of target
grid slots, never the number left after deleting missing data.

Every lag reports its coefficient, lag, count, denominator, coverage, and readiness.
The exploratory selected lag maximizes absolute correlation among supported lags;
ties choose the smallest lag. Searching six directions and several lags introduces
multiple-testing and selection bias. Timing convention labels do not imply causation,
a predictive model, tradeable latency, or profitable trading performance.

Optional `OOS_ENABLED=true` divides each rolling grid lookback chronologically into
the first 70% for training and the remaining 30% for testing, without random shuffling.
The ratio is fixed by configuration. Only training-target correlations select the
lag. That lag is frozen before evaluating later test targets; the split timestamp,
training/test coefficients, counts, and coverage are returned. Both segments require
at least 10 matched pairs and the configured coverage. Test leading observations may
precede the split, as they would already be known, but no test target enters training.
This is a held-out **association-stability** check, not forecast-error or trading
performance evaluation. Successive rolling splits overlap and are not independent
validation experiments. OOS is disabled by default; unsupported splits stay unavailable.

## Rule-based market regimes

Regimes require all three current correlations, all three established correlation
baselines, and all three established return-volatility baselines. Each volatility
baseline is the median of the preceding contiguous eligible rolling volatilities,
using the same history length/minimum support as relationship baselines.

```text
elevated asset: current return volatility > max(2 × historical median, 0.000001)
high synchronization: every signed pair correlation >= 0.8
relationship change: any supported breakdown event (either direction)
```

The precedence is:

1. Any required evidence/baseline unavailable: `insufficient_data`.
2. Multiple evidence categories active: `mixed_or_unstable`.
3. Supported relationship change only: `correlation_breakdown`.
4. Elevated volatility only: `elevated_volatility`.
5. High synchronization only: `high_synchronization`.
6. Supported evidence with none of those flags: `normal_observed_conditions`.

An insufficient regime distinguishes incomplete current data from insufficient
historical support. The result includes evidence time, thresholds, ready-pair count,
mean available signed correlation, elevated assets, changed pairs, quality, and an
explanation. “Normal” describes these particular observed rules; it does not certify
safe markets. No regime is a trading signal or crash forecast.

## Persistence, bounded processing, and identity

Migration to SQLite `user_version=3` adds only:

- `cross_profiles`: full cross policy JSON, source profile, durable publication
  checkpoint, snapshot count, last successful processing clock time.
- `cross_snapshots`: immutable result bundles keyed by `(profile_id, window_end)`
  with a deterministic content-independent evaluation ID.
- `cross_breakdown_events`: stable per-profile/time/pair event IDs and explanations.

The existing nine data tables, indexes, and Phase 2 statistical policy remain intact.
Migration is transactional, accepts versions 0/2 via the existing additive path,
and is preserved by the later explicit research migration to schema 4. Unknown future versions are refused. A failed migration rolls back the new objects
and version. The original Phase 2 migration test now expects schema version 3;
its raw-data and insertion-ledger preservation assertions remain.

The cross profile hashes the algorithm version, every cross statistical setting,
fixed asset universe, source profile ID, and candle duration. Changing a source or
cross policy starts isolated history. Operational batch size and poll interval do
not affect identity. Existing Phase 2 profile IDs are unchanged.

Each step loads at most the configured return lookback, maximum lag, preceding
close, and bounded cross baseline. Source queries use the existing
`(profile_id, symbol, window_start)` index; snapshot/event primary keys support
time-ordered reads. Calculations run on the dedicated SQLite worker thread under
a WAL read snapshot. The write lock is acquired only to compare-and-swap the
checkpoint and atomically persist the result and optional events. A competing
worker on the same profile fails visibly rather than duplicating output.

At most 128 snapshots are committed per worker pass. The one-shot CLI continues
bounded passes until caught up; watch mode then polls every five seconds. Ctrl+C
stops between atomic steps. Restart resumes from the durable event-time checkpoint.
No raw-trade rescan or recomputation of finalized history occurs on ordinary polling.

After an entire return lookback plus lag context contains no observed source
candles, the worker skips a wholly cold outage to the next observed candle end or
common safe frontier. `skipped_intervals` records omitted evaluation slots. Such
compaction never skips a supported relationship, bridges a return, invents an
eligible baseline, or labels an unknown period with a market regime. The chart
breaks lines across skipped times. The API returns discrete persisted snapshots,
not a claim that every missing minute was separately evaluated. Initial history
fetches use three indexed first-row reads once per new profile.

Status exposes source progress, pending/late counts, unstaged raw-input count,
common safe boundary, durable output checkpoint, remaining grid intervals, and
last successful processing time. This is processing evidence, not a process heartbeat.
If a source stalls, common progress stalls. No source is silently removed to make
the remaining relationships appear current. Stored history grows without a retention
policy; this local research implementation does not claim unlimited throughput.

## Configuration and commands

All statistical variables use the prefix `MARKETPULSE_CROSS_ASSET__` in `.env`.
Defaults and validation live in `cross_asset/config.py`; `.env.example` lists every
field. Key defaults are lookback 60, minimum pairs 30, minimum coverage 0.8, baseline
60/minimum 20, scale floor 0.05, deviation threshold 3.5, minimum change 0.2, maximum
lag 3, synchronization 0.8, volatility multiplier 2, and volatility floor 0.000001.
Operational settings are `MARKETPULSE_CROSS_ASSET_BATCH_SIZE=128` and
`MARKETPULSE_CROSS_ASSET_POLL_INTERVAL=5.0`. Invalid settings fail startup.

Use the same database, Phase 2 policy, and cross policy for the worker and API.
From the repository root, with the existing environment/dependencies installed:

```powershell
# Existing public trade collector, separate terminal when collecting new data
.\.venv\Scripts\python.exe -m marketpulse.ingestion.cli

# Existing Phase 2 worker, separate terminal
.\.venv\Scripts\python.exe -m marketpulse.analytics.cli --watch

# Phase 4: one-shot historical backfill (no exchange connection needed)
.\.venv\Scripts\python.exe -m marketpulse.cross_asset.cli

# Or Phase 4 continuous processing, separate terminal
.\.venv\Scripts\python.exe -m marketpulse.cross_asset.cli --watch

# Restart the API to load the new read-only routes
.\.venv\Scripts\python.exe -m uvicorn marketpulse.api.app:create_app --factory --host 127.0.0.1 --port 8000

# Frontend, separate terminal; visit http://127.0.0.1:5173/cross-asset
npm --prefix frontend run dev
```

The new optional `marketpulse-cross-asset` console entry point is installed when
the editable package metadata is refreshed. The explicit module commands above work
with the existing editable environment. Only one Phase 4 worker should run per profile.

## Read-only API

| GET route under `/api/cross-asset` | Contract |
| --- | --- |
| `/correlations?limit=100` | Newest-first frames with pair/asset statistics, coverage, time, and skipped intervals |
| `/matrix` | Current profile IDs, asset universe, readiness, latest full snapshot or null |
| `/breakdowns?limit=100&pair=BTCUSDT-ETHUSDT` | Stable relationship-change events; pair optional and canonical |
| `/lead-lag?leader=BTCUSDT&follower=ETHUSDT` | Latest ordered-pair lag curves and optional chronological evaluation; filters optional |
| `/regimes?limit=100` | Newest-first regime frames with profile and evidence |
| `/regimes/latest` | Latest regime frame or null |
| `/status` | Durable processing state, source boundaries, and explicit unknown heartbeat |

Lists are bounded to 1–1,000 results, default 100. Asset/pair filters are validated
enums; same-asset lead/follow requests return 422. Timestamps are aware UTC. Missing
statistics remain null with readiness metadata. Database failures return 503. All
original seven application endpoints preserve their existing representations.
OpenAPI/Pydantic models are the frontend's generated type source.

## Dashboard

The new **Cross-Asset Intelligence** destination reuses the existing design system,
TanStack Query polling, query error/cached-data states, and UTC freshness labels.
It includes:

- Interactive signed 3×3 matrix with sample counts and coverage. Self cells are
  labeled “Self”, not invented numeric discoveries.
- Pair history selection and Lightweight Charts plots. Separate line segments
  prevent visual interpolation across unavailable/compacted intervals.
- Three-node network using only supported calculated edges. Positive edges are
  solid green; negative edges are dashed red; width is `1 + 5 × |r|` for legibility.
  Pair count/coverage buttons and shared evidence freshness accompany the drawing.
- Ordered lead/follow selector, precise timing convention, per-lag support, and
  exploratory-selection/chronological-holdout explanations.
- Regime summary, threshold details, and a discrete timeline of the latest 20
  persisted regime frames, plus relationship-breakdown explanations and warm-up.
- Source/output progress and OneDrive location metadata, without claiming a live
  collector or worker from API reachability.

The browser fetches the latest 100 history/event/regime frames. These bounded views
are not all-time totals or a complete historical research export. No production
module imports synthetic fixtures.

## Validation commands

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe frontend/scripts/export_openapi.py --check
.\.venv\Scripts\python.exe frontend/scripts/export_test_fixtures.py --check
.\.venv\Scripts\python.exe frontend/scripts/export_cross_fixtures.py --check
```

When intentionally updating API contracts, export without `--check`, run
`npm --prefix frontend run api:generate`, then review the generated changes.
Cross fixtures are actual FastAPI responses from deterministic synthetic trades
in a temporary database. Only operational clock metadata is frozen there for
reproducible snapshots. They are never inserted into the real database.

From `frontend/`:

```powershell
npm run typecheck
npm run lint
npm test
npm run build
# API and Vite running, installed Chrome required:
npm run test:browser
```

Backend tests include positive/negative and constant series, insufficient support,
different starts, missing/partial/gap windows, zero returns, UTC offsets, duplicate
inputs, no future leakage, baseline warm-up/reset, signed changes, regime transitions,
lag direction/gap chains, chronological training isolation, atomic migration/output
rollback, bounded/restart/idempotent processing, source-frontier lag, profile isolation,
late data, nonblocking concurrent ingestion, preserved raw/ledger contents, API
validation, and the original endpoint compatibility tests.

Frontend tests include actual serialized contracts, empty/warm-up/error/cached states,
matrix/pair selection, signed and zero coefficients, network support, lag-direction
selection, threshold/event explanations, and chart-line segmentation. Browser tests
exercise all six pages against the real local API and separately exercise explicitly
intercepted synthetic populated research states on desktop and mobile Chrome.

## Research limitations

Real-market detection quality is unverified. At the initial implementation audit,
the stored data had only one synchronized eligible return, so that capture could
not support numeric correlations, lead–lag discoveries, or established regimes.
Collection has since continued; consult the live API/dashboard for current readiness.
The original audit is not a live status indicator, and warm-up requirements were not lowered.

Future research should evaluate rolling-window dependence/effective sample size,
false discovery across pairs/lags/times, regime/threshold calibration, nonstationarity,
asynchronous trading and candle-resolution effects, coverage-selection bias, extreme
returns, alternative robust estimators, and truly independent temporal holdouts.
Pearson correlation is sensitive to outliers and measures linear association only.
Survivorship/universe limitations are substantial with three assets. These are
evaluation concerns; Phase 5 algorithms and predictive models are not implemented.

The system does not certify exchange-clock integrity, complete coverage, calibrated
probabilities, causal transmission, contagion, or tradeable predictive skill. Other
browser engines, physical mobile devices, months-long operation, and stress throughput
remain separate verification work. There is no public deployment in this phase.

## References

- [NIST correlation reference](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/correlat.htm)
- [NIST exploratory data analysis handbook](https://www.itl.nist.gov/div898/handbook/)
- [TradingView Lightweight Charts series API](https://tradingview.github.io/lightweight-charts/docs/api/variables/LineSeries)
