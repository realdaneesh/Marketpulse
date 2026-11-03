import Decimal from "decimal.js";
import { config } from "../config";

export const FinancialDecimal = Decimal.clone({ precision: 100 });
export function decimal(value: string | null | undefined): string {
  if (value == null) return "—";
  try {
    // No conversion through binary floats; retain every meaningful decimal digit.
    const expanded = new FinancialDecimal(value).toFixed();
    const [whole, fraction] = expanded.split(".");
    return (
      whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
      (fraction ? `.${fraction}` : "")
    );
  } catch {
    return "—";
  }
}
export const number = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(value)
    ? "—"
    : value.toLocaleString("en-US", { maximumFractionDigits: digits });
export const percent = (value: number | null | undefined) =>
  value == null ? "—" : `${number(value * 100, 4)}%`;
export function utc(
  value: string | number | null | undefined,
  milliseconds = false,
): string {
  if (value == null) return "Not recorded";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Unknown timestamp";
  return (
    date
      .toISOString()
      .replace("T", " ")
      .slice(0, milliseconds ? 23 : 19) + " UTC"
  );
}
export function freshness(value: string | null | undefined, now: number) {
  if (!value) return { label: "No observation", tone: "neutral" };
  const age = (now - new Date(value).getTime()) / 1000;
  if (!Number.isFinite(age)) return { label: "Unknown time", tone: "neutral" };
  if (age < -5) return { label: "Clock ahead", tone: "warning" };
  if (age <= config.staleSeconds)
    return { label: "Recent observation", tone: "positive" };
  const elapsed =
    age >= 86400
      ? `${Math.floor(age / 86400)}d`
      : age >= 3600
        ? `${Math.floor(age / 3600)}h`
        : `${Math.floor(age / 60)}m`;
  return { label: `Stale · ${elapsed} ago`, tone: "warning" };
}
export const humanize = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase());
export function severity(score: number | null | undefined) {
  return score == null
    ? "Unavailable"
    : score >= 75
      ? "High"
      : score >= 50
        ? "Elevated"
        : "Low";
}
