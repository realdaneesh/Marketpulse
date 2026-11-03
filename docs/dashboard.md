# Financial intelligence dashboard

The frontend lives in `frontend/` and uses React, TypeScript, Vite, Tailwind CSS,
TanStack Query, React Router, Lucide React and TradingView Lightweight Charts.
Phases 3-5 provide seven pages over 23 read-only API routes. All production views
use actual backend responses; explicitly synthetic fixtures live only in testing
and screenshot demonstrations.

## Views and data contracts

| Route | Content | API source |
| --- | --- | --- |
| `/` | BTC/ETH/SOL cards, latest observed prices, latest finalized window volume and trades, readiness, alerts, recent tape | Trades, latest analytics, recent anomalies, summary |
| `/markets` | Symbol selection, UTC candles and quote-volume histogram, range controls, exact OHLC readout, window metrics, latest 100 trades | Candles, trades, symbols |
| `/anomalies` | Recent events, market/severity filters, contributions, explanations, latest detector metrics and baseline statistics | Events, summary, latest analytics, symbols |
| `/analytics` | Volume, realized volatility, signed imbalance, log returns, observation table, latest detector statistics | Candles, latest analytics, symbols |
| `/system` | API/database probe, latest recorded trade, per-symbol processed-event and finalized timestamps, pending/late counts, subscription configuration | Health, trades, latest analytics, symbols |
| `/cross-asset` | Correlation matrix/history, signed network, lead-lag, regimes and relationship evidence | Cross-asset endpoints |
| `/research` | Experiments, detector evaluation, change points, sequences, discoveries and evidence | Versioned research endpoints |

`frontend/openapi.json` is exported from `create_app().openapi()` without entering
the app lifespan or opening a database. `src/api/schema.d.ts` is generated from
that snapshot with `openapi-typescript`; response aliases live in `src/api/types.ts`.
The client uses the backend's actual arrays and objects without adding envelope
fields. Requests are GET-only, cancellable, have a 15-second timeout, and reject
HTTP errors and non-JSON proxy fallbacks. TypeScript types are compile-time contracts,
not a runtime schema validator.

Regenerate contracts from the repository root when backend schemas change:

```powershell
.\.venv\Scripts\python.exe frontend/scripts/export_openapi.py
Set-Location frontend
npm run api:generate
Set-Location ..
```

Check for backend drift without modifying the snapshot:

```powershell
.\.venv\Scripts\python.exe frontend/scripts/export_openapi.py --check
```

## Configuration and launch

Follow the four terminal commands in the root README. Run backend processes from
the repository root and frontend commands from `frontend/`. Node 22.12+ is required;
`npm ci` installs the committed dependency lockfile.

Copy `frontend/.env.example` to `frontend/.env` if overriding defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MARKETPULSE_API_TARGET` | `http://127.0.0.1:8000` | Vite development/preview proxy destination; not exposed to browser code |
| `VITE_API_BASE_URL` | Empty | Browser API origin/prefix; empty uses same-origin `/api` and `/health` |
| `VITE_POLL_INTERVAL_MS` | `5000` | Query interval; minimum 1000 ms; invalid values use default |
| `VITE_STALE_AFTER_SECONDS` | `60` | Event-time freshness threshold; minimum 1 second |

`VITE_*` values are public build-time configuration. Restart Vite after changing
the environment; rebuild production output when changing these values. The app
does not use exchange credentials. Background tabs pause interval polling, and
refocusing refreshes stale queries. Manual refresh invalidates active queries.

`npm run build` emits `frontend/dist/`. `npm run preview` serves that output locally
at port 4173 with the same API proxy. For separate production hosting, configure a
same-origin reverse proxy for `/api/*` and `/health` and an SPA fallback for the five
client routes. The Vite development proxy is not bundled into `dist/`. An external
API origin would need explicit CORS configuration; none is added in Phase 3.
Authentication and public deployment hardening remain outside this scope.

## Data interpretation

- Monetary strings are formatted with decimal arithmetic; formatting does not
  convert prices or quantities through binary floats. Insignificant trailing zeros
  are removed. Large int64 trade IDs retain their original digits during JSON parsing.
- Chart coordinates necessarily use JavaScript numbers and are approximate. Exact
  source OHLC/volume values appear in the crosshair readout and tables. Values that
  overflow or underflow numeric chart coordinates are omitted, not drawn as zero.
- Charts show finalized backend windows at the configured interval. 1H/6H/24H
  ranges end at the latest fetched candle, allowing historical captures to be inspected.
  The endpoint returns at most 1,000 newest windows, with no cursor or date filter;
  a selected range may therefore be truncated. “All fetched” means those returned
  windows, not all stored history. The frontend does not resample intervals.
- Missing windows are whitespace, not zero activity. Partial starts and gap candles
  are colored amber on price and volume charts. Statistical plots retain null metrics;
  the window table and quality notice expose incomplete coverage. Known-volume sums
  include marked partial windows and exclude null volume; they are not exchange totals.
- All timestamps and chart times are UTC. Trade tables include milliseconds.
  Freshness uses source event timestamps and the browser's clock, never HTTP success
  time. A future timestamp beyond five seconds gets a clock-ahead label.
- Loading, empty, unavailable, stale, and API failure states are distinct. Background
  refresh failures retain cached data with the last successful fetch time and a warning.
  Health is marked unknown after a failed probe, even if an older success is cached.
- The collector connection and worker process heartbeat are not exposed by the API.
  They remain unknown. API reachability, recent trades, and analytics readiness do not
  prove the collector currently has a Binance connection.
- Alert summaries cover at most 100 recent combined alerts, not an all-time count.
  Severity filters apply to this fetched event list. Display categories are Low below
  50, Elevated from 50 to below 75, and High from 75 through 100. The backend's
  configurable alert threshold remains separate and is shown in event details.
- Null risk/contribution values remain unavailable, whereas ready zero scores are
  shown as zero. No missing indicator is renormalized by the frontend. The API exposes
  latest per-detector metrics, median, MAD, scale, threshold, and history count, but
  does not expose historical detector hit rates. Scores are severity heuristics,
  not calibrated probabilities, forecasts, or investment advice.

## Verification

From `frontend/`:

```powershell
npm run typecheck
npm run lint
npm test
npm run build
```

Vitest + React Testing Library cover precision, unsafe IDs, UTC offsets, freshness,
null versus zero, chart ordering and missing data, range anchoring, read-only API
contracts, HTTP/JSON failures, cancellation, polling, loading/empty states,
readiness, severity filters, market switching, retries, cached-data errors,
navigation, focus restoration, and truthful collector status.

MSW intercepts requests only in tests. Test responses are produced by the actual
FastAPI app and analytics worker using a temporary, explicitly synthetic database.
No fixture data is imported by production application modules. To refresh or check
these serialized test responses, from the repository root:

```powershell
.\.venv\Scripts\python.exe frontend/scripts/export_test_fixtures.py
.\.venv\Scripts\python.exe frontend/scripts/export_test_fixtures.py --check
```

With Chrome installed and the API plus Vite running, from `frontend/`:

```powershell
npm run test:browser
```

Playwright exercises all five pages against the real local API on desktop and
an emulated mobile viewport, checks for horizontal page overflow and JavaScript
errors, tests navigation, selectors, and intercepted API failures/recovery, and
writes screenshots to ignored `frontend/test-results/`. A separately named fixture
test exercises populated charts and anomaly events without writing to the real database.
Set `DASHBOARD_URL=http://127.0.0.1:4173` to target the local production preview instead.

From the repository root, recheck the backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Phase 3 does not start collection automatically, extend the recorded dataset, change
warm-up requirements, introduce machine learning, or add trading capabilities.
The existing 6,039-trade capture supports only partial initial candles and insufficient
detector history. Real sustained-market detection quality, long-running polling under
load, other browser engines, and physical mobile devices require separate validation.

## API overview

There are 23 read-only GET endpoints. Interactive endpoint schemas are available
from the local API at `/docs` and the committed `frontend/openapi.json` snapshot.

| Group | Routes |
| --- | --- |
| Original seven | `/health`, `/api/trades/recent`, `/api/market/symbols`, `/api/analytics/candles`, `/api/analytics/latest`, `/api/anomalies/recent`, `/api/anomalies/summary` |
| Cross-asset seven | `/api/cross-asset/correlations`, `/matrix`, `/breakdowns`, `/lead-lag`, `/regimes`, `/regimes/latest`, `/status` (all share the cross-asset prefix) |
| Research nine | `/api/research/v1/status`, `/experiments`, `/experiments/{id}`, `/experiments/{id}/metrics`, `/experiments/{id}/change-points`, `/experiments/{id}/sequences`, `/experiments/{id}/discoveries`, `/discoveries/{id}`, `/discoveries/{id}/evidence` (all share the research prefix) |

Detail routes use real experiment/discovery IDs from their corresponding lists.
A fresh database has no such IDs; its list routes return empty results. Research
status explains an uninstalled schema; research data routes require schema 4.
Readiness, filters and bounds are documented in the
[cross-asset](cross_asset_intelligence.md) and [research](research_validation.md) guides.

## Implementation references

- [Tailwind CSS Vite integration](https://tailwindcss.com/docs/installation/using-vite)
- [Lightweight Charts v5 series API](https://tradingview.github.io/lightweight-charts/docs/migrations/from-v4-to-v5)

The chart library attribution logo is retained, with a TradingView link in chart views.
