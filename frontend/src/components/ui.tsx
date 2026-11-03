import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowUpRight,
  Clock3,
  Database,
  RefreshCw,
} from "lucide-react";
import { Link } from "react-router";
import { freshness, humanize, number, utc } from "../lib/format";
import { useNow } from "../lib/clock";
import type { Risk } from "../api/types";
import { detectorNames } from "../config";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}
export function Freshness({ timestamp }: { timestamp?: string | null }) {
  const state = freshness(timestamp, useNow());
  return (
    <span title={utc(timestamp)}>
      <Badge tone={state.tone}>{state.label}</Badge>
    </span>
  );
}
export function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Database size={25} strokeWidth={1.3} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function QueryState<T>({
  query,
  children,
}: {
  query: UseQueryResult<T, Error>;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="loading" role="status">
        <span className="skeleton" />
        <span className="skeleton" />
        <span>Loading recorded data…</span>
      </div>
    );
  if (query.data === undefined)
    return (
      <div className="error-state" role="alert">
        <AlertCircle size={20} />
        <div>
          <strong>Data unavailable</strong>
          <p>{query.error?.message || "No response received."}</p>
        </div>
        <button className="button small" onClick={() => void query.refetch()}>
          <RefreshCw size={14} />
          Retry
        </button>
      </div>
    );
  return (
    <>
      {query.isError && (
        <div className="notice warning" role="alert">
          <AlertCircle size={16} />
          <span>
            Refresh failed. Showing cached data from {utc(query.dataUpdatedAt)}.
          </span>
          <button className="text-button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      )}
      {children(query.data)}
    </>
  );
}
export function Metric({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}) {
  return (
    <div className="metric">
      <span className="label">{label}</span>
      <strong className={tone}>{value}</strong>
      {hint && <span className="metric-hint">{hint}</span>}
    </div>
  );
}
export function InlineLink({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}) {
  return (
    <Link className="inline-link" to={to}>
      {children}
      <ArrowUpRight size={15} />
    </Link>
  );
}
export function RiskScore({ risk }: { risk?: Risk | null }) {
  const score = risk?.score;
  return (
    <div className="risk-score">
      <strong
        className={
          score == null
            ? "muted"
            : score >= 75
              ? "negative-text"
              : score >= 50
                ? "warning-text"
                : "accent-text"
        }
      >
        {number(score, 1)}
      </strong>
      <span>/ 100</span>
      <span className="muted">
        {risk ? humanize(risk.status) : "Awaiting evaluation"}
      </span>
    </div>
  );
}
export function Contributions({ risk }: { risk: Risk }) {
  return (
    <div className="contributions">
      {risk.contributions.map((item) => (
        <div key={item.detector}>
          <div className="flex items-center justify-between gap-3">
            <span>{detectorNames[item.detector]}</span>
            <span className="mono">
              {item.points == null
                ? humanize(item.status)
                : `${number(item.points)} pts`}
            </span>
          </div>
          <div
            className="meter"
            role="img"
            aria-label={`${detectorNames[item.detector]}: ${item.points == null ? "unavailable" : `${item.points} points out of 100`}`}
          >
            <span style={{ width: `${item.points ?? 0}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
export function Timestamp({ value }: { value?: string | null }) {
  return (
    <span className="timestamp">
      <Clock3 size={12} />
      <time dateTime={value ?? undefined}>{utc(value)}</time>
    </span>
  );
}
