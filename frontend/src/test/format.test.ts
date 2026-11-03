import { describe, expect, it } from "vitest";
import { decimal, freshness, percent, severity, utc } from "../lib/format";

describe("financial and timestamp presentation", () => {
  it("retains significant decimal digits without passing through Number", () => {
    expect(decimal("12345678901234567890.123456789123456789")).toBe(
      "12,345,678,901,234,567,890.123456789123456789",
    );
    expect(decimal("0.000000000000000000123456789")).toBe(
      "0.000000000000000000123456789",
    );
    expect(decimal("1.23456789E-8")).toBe("0.0000000123456789");
    expect(decimal("100.0000")).toBe("100");
  });
  it("distinguishes unavailable values from zero", () => {
    expect(decimal(null)).toBe("—");
    expect(decimal("0")).toBe("0");
    expect(percent(null)).toBe("—");
    expect(percent(0)).toBe("0%");
  });
  it("converts timezone offsets to UTC including milliseconds", () => {
    expect(utc("2024-01-01T05:30:00.123+05:30", true)).toBe(
      "2024-01-01 00:00:00.123 UTC",
    );
    expect(utc(null)).toBe("Not recorded");
  });
  it("uses event time for freshness and detects clock skew", () => {
    const now = Date.parse("2024-01-01T00:02:00Z");
    expect(freshness("2024-01-01T00:01:45Z", now).label).toBe(
      "Recent observation",
    );
    expect(freshness("2024-01-01T00:00:00Z", now).label).toBe("Stale · 2m ago");
    expect(freshness("2024-01-01T00:03:00Z", now).label).toBe("Clock ahead");
    expect(freshness(null, now).label).toBe("No observation");
  });
  it("applies documented display severity boundaries", () => {
    expect([null, 0, 49.9, 50, 74.9, 75, 100].map(severity)).toEqual([
      "Unavailable",
      "Low",
      "Low",
      "Elevated",
      "Elevated",
      "High",
      "High",
    ]);
  });
});
