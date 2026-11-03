# Phase 2: statistical market anomaly intelligence

This phase adds a local analytics worker and four read-only APIs. It uses the raw
trades already stored by Phase 1. Statistics are descriptive and explainable;
they do not place orders or predict future returns. Standard-library numerical
tools are sufficient here; no new third-party dependencies are needed.

## Event-time and completeness policy

Windows are UTC, epoch-aligned, half-open intervals `[start, end)`, 60 seconds by
default. A trade exactly at `end` belongs to the next interval. Symbols are processed
independently. Duplicate exchange/symbol/trade IDs remain excluded by the original
raw-trade primary key. Equal timestamps are ordered deterministically by trade ID.

For each symbol, the worker tracks the maximum **committed trade event timestamp**
seen in its input snapshot. Its watermark is:

```text
watermark = maximum observed event timestamp - allowed lateness (default 10 seconds)
```

A window can be finalized only when `end <= watermark`. Advancing the wall clock,
polling the database, exiting a batch run, or restarting the worker never advances
this watermark. The latest window may remain pending indefinitely without new
trades. A new event supplies evidence of event-time progress; its price/volume is
never included in earlier windows or their statistical baselines.

Before finalization, records can arrive in any order and are sorted by event time
when aggregated. Each pass captures a finite insertion-sequence upper bound and
stages every record through that bound before finalizing anything. This avoids
finalizing based only on an earlier page of an out-of-order historical snapshot.

Finalized candles/results are immutable for a policy profile. A subsequently
committed trade with a timestamp before that symbol's finalized boundary remains
in raw storage and is recorded in `analytics_late_trades`; it cannot retrospectively
change scores, baselines, or alerts. The latest API exposes the late-record count.
This intentionally means a later offline replay in a **different policy profile**
can see a different dataset than the earlier online decision. Results describe
the information accepted at finalization, not a reconstructed perfect exchange tape.

### Coverage quality

| Quality | Meaning and statistical treatment |
| --- | --- |
| `partial_start` | First observed interval has unknown start coverage; excluded from baselines and alerts. |
| `observed` | Finalized by the watermark, with no detected trade-ID gap; eligible for statistics. This does not certify complete exchange coverage. |
| `data_gap` | Nonconsecutive trade IDs within/across adjacent windows, or the first window after a missing range; excluded. |
| `missing` | No collected trades across one or more intervals. Volumes and prices are null; `missing_intervals` records the range length. |

Missing ranges are compacted into one row with explicit start/end boundaries, so
a long outage does not manufacture millions of empty zero-volume candles. Baselines
restart after missing/incomplete intervals; missing market observations are never
treated as zero activity. No gaps are invented before the first observed interval
or after the latest available event-time evidence.

The feed has no historical backfill or authoritative coverage metadata. Reconnects
may lose data. Missing intervals and nonconsecutive Binance per-symbol trade IDs
detect many losses, including sub-minute gaps, but cannot prove perfect coverage.
Trade-ID continuity assumes Binance's individual trade stream semantics; unexpected
ID discontinuities conservatively suppress affected analytics. Late trades do not
repair already finalized quality. The original partial-start interval is excluded
even if its first timestamp happens to lie on an exact minute boundary.

## Aggregation definitions

Prices, quantities, summed volumes, quote notional and VWAP use Decimal with a
50-digit arithmetic context; they serialize as decimal strings. Statistical
metrics use finite Python floating-point values. The database worker streams each
ordered window with bounded fetches into a constant-memory accumulator.

For trades `(price_i, quantity_i)`:

- Open/close: prices of the first/last event, with trade-ID tie breaking.
- High/low: extrema of observed trade prices.
- Base volume: `sum(quantity_i)`.
- Quote volume: `sum(price_i * quantity_i)`.
- Aggressive buy volume: base quantity where `buyer_maker=false`.
- Aggressive sell volume: base quantity where `buyer_maker=true`.
- VWAP: quote volume / base volume; null for zero volume.
- Signed imbalance: `(buy_volume - sell_volume) / base_volume`, in `[-1, 1]`;
  null for zero volume.
- Candle log return: `ln(current_close / previous_close)` only for adjacent,
  eligible candles of the same symbol. Missing/partial predecessors yield null.
- Realized volatility: `sqrt(sum(ln(price_i / price_(i-1)) ** 2))` over the `n-1`
  **within-window** trade-price changes. This is unannualized, not standard
  deviation and not a forecast. Fewer than two trades yields null. Cross-window
  jumps are reflected by the candle-return detector rather than this measure.

The bounded-input convenience aggregator sorts and deduplicates records. Conflicting
duplicates are rejected. Production processing relies on raw database uniqueness
and the indexed ordered cursor, without loading all historical trades into memory.

## Rolling detectors and leakage prevention

Every result includes symbol, UTC boundaries, detector, observed metric, historical
median, MAD, effective scale, history count, anomaly score, threshold, status,
anomaly flag, and explanation. Null fields explicitly indicate unavailable evidence.

The default baseline uses up to 60 preceding contiguous eligible windows and requires
20 eligible metric observations. **The evaluated window is never in its own
baseline.** Future, overlapping, other-symbol, and different-duration windows are
excluded defensively. Missing/incomplete intervals break the contiguous run.
Null metrics are skipped, not imputed. The same historical window can contribute
to one detector but not another; each detector has an independent readiness count.

For observed metric `x` and historical metrics `H`:

```text
m = median(H)
MAD = median(abs(h - m) for h in H)
scale = max(1.4826 * MAD, abs(m) * relative_scale_floor, detector_absolute_floor)
z = clip((x - m) / scale, -100, 100)
anomaly_score = max(0, z)
```

Default `relative_scale_floor=0.01`; absolute floors are 1 quote unit for volume,
0.000001 for volatility and price shock, and 0.01 for imbalance. These are explicit
stabilizing assumptions, especially for zero-MAD/flat baselines—not estimates of
statistical significance. Equal constant observations score zero. A large departure
from a flat baseline produces a finite capped score. Nonfinite/out-of-range metrics
are unavailable rather than alerts. The default threshold is 3.5 for all detectors.

| Detector | Metric and additional gates |
| --- | --- |
| Volume | Quote notional; detects upper-tail increases only. |
| Volatility | Within-window realized volatility; decreases do not trigger. |
| Imbalance | Absolute signed imbalance compared with historical absolute imbalance. Observed metric retains its sign. Current and baseline samples require at least 20 trades and 1,000 quote notional; an alert also requires absolute imbalance >= 0.8. |
| Price shock | Absolute candle log return compared with historical absolute returns. Observed metric retains its sign; both up/down shocks can qualify. |

Statuses are `ready`, `insufficient_history`, `incomplete_window`,
`insufficient_activity`, or `unavailable_metric`. During warm-up `is_anomaly=false`
and score is null. Sparse one-sided flow does not silently become a normal result;
it is unavailable for imbalance. All these gates and constants are configurable.

## Combined evidence score

Each detector has a configurable positive weight. Defaults are equal. For a ready
detector that passed its anomaly gates:

```text
severity_i = clip(anomaly_score_i / threshold_i - 1, 0, 1)
contribution_i = 100 * weight_i / sum(all configured weights) * severity_i
combined_score = sum(contribution_i)
```

A normal ready detector contributes **0**. An unavailable detector contributes
**null**, with its status retained. Weights are never renormalized around missing
indicators. Full contribution occurs at twice the detector threshold. With four
equal weights, one detector contributes at most 25 points.

By default **all four detectors are required**. If any required indicator is not
ready, combined score is null and no combined alert is emitted, even if other
detectors show strong evidence. Users may explicitly configure a required subset;
unavailable optional contributions remain null and use the same fixed denominator.
The default combined alert threshold is 50 out of 100.

This is a transparent severity heuristic. It is **not a calibrated probability of
a crash, fraud, manipulation, or future price movement**. Results carry explanations
and individual contributions so a caller can see what created the score.

## Persistence, bounded work, and restart behavior

Opening the database performs an additive transactional migration to SQLite
`user_version=2`. The original `trades` table and API representation are preserved.
Migration failure rolls back the new objects/version, and a newer unknown schema
version is refused. A pre-migration backup is recommended; the development run
created `data/phase1-before-analytics.sqlite3` before extending the real database.

New tables:

- `trade_changes`: durable AUTOINCREMENT insertion ledger with unique raw-trade
  identity, backfilled once and maintained by an insert trigger. Explicit sequence
  IDs survive VACUUM. Raw duplicate inserts do not create ledger entries.
- `analytics_profiles`: complete policy JSON and incremental ingestion checkpoint.
- `analytics_symbol_state`: per-profile/symbol event progress and finalized boundary.
- `analytics_pending`: disk-backed references to staged trades awaiting finalization.
- `analytics_late_trades`: durable late-data exclusion audit, without deleting raw data.
- `market_windows`: finalized candles/gap ranges and combined assessments.
- `detector_results`: one result per window/detector.
- `anomaly_events`: combined alerts only, with stable window/profile-derived IDs.

Policy identifiers hash the algorithm version and all statistical/finalization
settings. Changing a policy creates an isolated profile and processes its history
once. Old results remain stored, but API queries use the current configured profile.
Page size, poll interval, and per-pass work cap do not change profile IDs. The worker
processes all persisted symbols; the unfiltered latest endpoint lists the configured
subscription symbols. Explicit symbol filters can inspect other persisted symbols.

Each page advances staging and its checkpoint atomically. Results, detector rows,
optional event, pending-row cleanup, and the finalization boundary are committed
atomically per window. A failed step can be retried without partial results or
duplicate events. Indexed keyset pagination reads only insertion sequences newer
than the checkpoint. History queries load at most the configured baseline length.
No `OFFSET` scans or full historical rescans occur on ordinary restarts.

Aggregation runs on the existing dedicated SQLite worker thread in a WAL **read**
snapshot. It does not hold the write lock while calculating. The commit phase briefly
takes the write lock and verifies that the profile checkpoint/finalization boundary
has not changed. Concurrent workers for the same profile fail visibly on conflict;
run one per profile. Ingestion and API connections can operate concurrently.
Large historical staging still consumes disk space and transaction time; this is
not a claim of unlimited throughput. Source trades are treated as immutable; raw
updates/deletes or ledger pruning are unsupported and require an explicit future
retention/rebuild design.

Default staging pages contain 2,000 trades. At most 1,000 windows finalize per pass;
the CLI continues additional passes until caught up. A historical command therefore
drains the eligible backlog; `--watch` continues polling every two seconds. New raw
commits after a pass's captured upper bound are processed on the next pass. Ctrl+C
stops between atomic steps, leaving a resumable checkpoint. Analytics never forces
the last pending window closed just to finish a historical run.

## Configuration and API

Use `MARKETPULSE_ANALYTICS__...` for fields in `AnalyticsConfig`; nested map settings
accept JSON. `.env.example` lists defaults. All worker/API processes must agree on
the database path and policy. Prices/volumes serialize as decimal strings; statistical
scores and returns serialize as numbers or null.

| Endpoint | Response |
| --- | --- |
| `/api/analytics/candles` | Latest finalized candles/gap ranges, newest start first. |
| `/api/analytics/latest` | Latest candle, four detector results, combined assessment, event progress, pending and late counts per symbol. No data returns `insufficient_history`. |
| `/api/anomalies/recent` | Combined alerts only, newest first, with stable IDs. |
| `/api/anomalies/summary` | Counts by symbol, maximum score, and latest event end within a bounded recent-alert sample. It is explicitly not an all-time total. |

All accept an optional case-insensitive alphanumeric `symbol` and a bounded `limit`
(default 100, range 1–1000). On `latest`, limit caps the number of returned symbols.
Invalid inputs return 422; database read errors return 503. OpenAPI response models
are available at `/docs`. The existing Phase 1 routes remain unchanged.

## Verification

The Phase 2 implementation run on Windows/CPython 3.14.2 passed **112 automated
tests**, including all original 54 tests, plus Ruff lint, Ruff formatting checks,
and `pip check`. All seven application endpoints returned HTTP 200 through a real
local Uvicorn server, and the new OpenAPI response models were checked.

Raw-trade content was hashed in deterministic exchange/symbol/ID order before and
after migration: all 6,039 records matched exactly. SQLite integrity passed. A second
analytics run staged zero records and finalized zero additional windows. No services
were left running after verification. No new Binance connection was needed.

The automated suite uses deterministic synthetic fixtures; no synthetic data is
inserted into the live database. It covers all four detectors, arithmetic, missing
data and sample-size gates, ordering, no future leakage, checkpoint restarts,
idempotence, policy isolation, safe migration/rollback, concurrent ingestion during
aggregation, stable alerts, backup refusal to overwrite, and API validation.

The original live data was processed after a verified backup. It produces three
`partial_start` windows, one per symbol, and leaves later incomplete intervals pending.
All three symbols report `insufficient_history`, every combined score is null,
and there are **zero anomaly events**. The 20-second capture cannot support meaningful
rolling baselines. Collect sustained data for at least the configured number of
eligible observations for every required detector; return baselines need additional
adjacent candles, and gaps restart warm-up. Do not lower warm-up just to manufacture
alerts from this capture.

Synthetic tests validate mechanics, not real-market detection quality. Detector
threshold calibration, extended reconnect coverage, sustained throughput, and
false-positive analysis remain future validation work. The original Phase 1 live
verification still stands; Phase 2 verification does not require another exchange
connection and does not claim newly observed live anomalies.

## References

- [Python statistics: median](https://docs.python.org/3/library/statistics.html#statistics.median)
- [NIST: outlier detection assumptions and interpretation](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm)
- [SQLite: explicit AUTOINCREMENT guarantees](https://www.sqlite.org/autoinc.html)
