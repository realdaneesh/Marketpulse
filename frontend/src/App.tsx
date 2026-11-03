import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import {
  Activity,
  BarChart3,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  LayoutDashboard,
  Menu,
  Network,
  Radio,
  RefreshCw,
  ScanLine,
  X,
} from "lucide-react";
import { NavLink, Route, Routes, useLocation } from "react-router";
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useHealth } from "./api/queries";
import { Badge } from "./components/ui";
import { useNow } from "./lib/clock";
import { utc } from "./lib/format";
const Overview = lazy(() => import("./pages/Overview"));
const Markets = lazy(() => import("./pages/Markets"));
const Intelligence = lazy(() => import("./pages/Intelligence"));
const Analytics = lazy(() => import("./pages/Analytics"));
const System = lazy(() => import("./pages/System"));
const CrossAsset = lazy(() => import("./pages/CrossAsset"));
const ResearchLab = lazy(() => import("./pages/ResearchLab"));
const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard, section: "01" },
  { to: "/markets", label: "Markets", icon: BarChart3, section: "02" },
  {
    to: "/anomalies",
    label: "Anomaly Intelligence",
    icon: ScanLine,
    section: "03",
  },
  { to: "/analytics", label: "Analytics", icon: Activity, section: "04" },
  { to: "/system", label: "System Status", icon: Radio, section: "05" },
  {
    to: "/cross-asset",
    label: "Cross-Asset Intelligence",
    icon: Network,
    section: "06",
  },
  { to: "/research", label: "Research Lab", icon: FlaskConical, section: "07" },
];
class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Dashboard rendering failed", error, info.componentStack);
  }
  render() {
    return this.state.failed ? (
      <div className="error-state" role="alert">
        <div>
          <h1>This view could not render</h1>
          <p>
            Reload the page to retry. Check browser support if chart rendering
            continues to fail.
          </p>
          <button className="button" onClick={() => window.location.reload()}>
            Reload dashboard
          </button>
        </div>
      </div>
    ) : (
      this.props.children
    );
  }
}
export default function App() {
  const [menu, setMenu] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLElement>(null);
  const location = useLocation();
  const queryClient = useQueryClient();
  const fetching = useIsFetching();
  const health = useHealth();
  const now = useNow();
  const current =
    navigation.find((item) => item.to === location.pathname)?.label ??
    "Page not found";
  useEffect(() => {
    document.title = `${current} · MarketPulse`;
  }, [current]);
  useEffect(() => {
    if (!menu) return;
    const previousOverflow = document.body.style.overflow;
    const trigger = menuButton.current;
    document.body.style.overflow = "hidden";
    const elements = drawer.current?.querySelectorAll<HTMLElement>("a, button");
    elements?.[0]?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenu(false);
      if (event.key === "Tab" && elements?.length) {
        const first = elements[0],
          last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKey);
      trigger?.focus();
    };
  }, [menu]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {menu && (
        <div className="drawer-backdrop" onClick={() => setMenu(false)} />
      )}
      <aside
        id="navigation"
        ref={drawer}
        className={`sidebar ${menu ? "open" : ""}`}
        role={menu ? "dialog" : undefined}
        aria-modal={menu || undefined}
        aria-label="Main navigation"
      >
        <NavLink to="/" className="brand" onClick={() => setMenu(false)}>
          <span className="brand-mark">
            <Activity size={22} strokeWidth={2.4} />
          </span>
          <span>
            Market<span className="brand-light">Pulse</span>
            <small>MARKET INTELLIGENCE</small>
          </span>
        </NavLink>
        <button
          className="close-menu icon-button"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        >
          <X size={20} />
        </button>
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          {navigation.map(({ to, label, icon: Icon, section }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setMenu(false)}
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
            >
              <Icon size={18} strokeWidth={1.7} />
              <span>{label}</span>
              <span className="nav-number">{section}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="environment">
            <span className="eyebrow">OBSERVATION MODE</span>
            <div>
              <span className="status-dot" />
              Public market data
            </div>
            <p>Read-only · Binance Spot</p>
          </div>
          <NavLink
            to="/system"
            className="help-link"
            onClick={() => setMenu(false)}
          >
            <CircleHelp size={16} />
            Data & system health
            <ChevronRight size={14} />
          </NavLink>
          <div className="sidebar-footer">
            <span className="mini-brand">MP</span>
            <div>
              MarketPulse<small>Phase 03 · Intelligence</small>
            </div>
            <span className="version">v0.3</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              ref={menuButton}
              className="mobile-menu icon-button"
              aria-label="Open navigation"
              aria-controls="navigation"
              aria-expanded={menu}
              onClick={() => setMenu(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{current}</strong>
          </div>
          <div className="topbar-tools">
            <span className="header-clock mono">{utc(now)}</span>
            <Badge
              tone={
                health.isError
                  ? "negative"
                  : health.data?.status === "ok"
                    ? "positive"
                    : "neutral"
              }
            >
              {health.isError
                ? "API unavailable"
                : health.data?.status === "ok"
                  ? "API reachable"
                  : "Checking API"}
            </Badge>
            <button
              className="icon-button"
              aria-label="Refresh dashboard data"
              title="Refresh all active queries"
              disabled={fetching > 0}
              onClick={() => void queryClient.invalidateQueries()}
            >
              <RefreshCw size={17} className={fetching ? "animate-spin" : ""} />
            </button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <ErrorBoundary key={location.pathname}>
            <Suspense
              fallback={
                <div className="loading" role="status">
                  Loading workspace…
                </div>
              }
            >
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/markets" element={<Markets />} />
                <Route path="/anomalies" element={<Intelligence />} />
                <Route path="/analytics" element={<Analytics />} />
                <Route path="/system" element={<System />} />
                <Route path="/cross-asset" element={<CrossAsset />} />
                <Route path="/research" element={<ResearchLab />} />
                <Route
                  path="*"
                  element={
                    <div className="empty">
                      <h1>Page not found</h1>
                      <NavLink to="/" className="inline-link">
                        Return to overview
                      </NavLink>
                    </div>
                  }
                />
              </Routes>
            </Suspense>
          </ErrorBoundary>
          <footer className="main-footer">
            <span>
              MARKETPULSE<span className="footer-divider">/</span>Observe.
              Understand. Stay informed.
            </span>
            <span>
              All timestamps UTC · Statistical evidence, not investment advice
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
