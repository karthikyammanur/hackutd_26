import { humanize } from "@/lib/simulate/labels";

/** Status colours, always shown with a text label. */
export const TIER_COLORS: Record<string, string> = { safe: "#0ca30c", uncertain: "#fab219", dangerous: "#d03b3b" };
export const TIER_ORDER = ["safe", "uncertain", "dangerous"] as const;

/** Colours follow the entity, so a filter can never repaint a series. Validated for colour-blind separation. */
export const CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"];
export const OTHER_COLOR = "#a8a8a8";

export const FAMILY_COLORS: Record<string, string> = {
  impersonation: CATEGORICAL[0],
  payment_lure: CATEGORICAL[1],
  credential_theft: CATEGORICAL[2],
  relationship_or_opportunity: CATEGORICAL[3],
  none: CATEGORICAL[4],
};

const pad = (value: number) => String(value).padStart(2, "0");

export function formatHour(value: string | null): string {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const day = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  return `${day}, ${pad(date.getUTCHours())}:00 UTC`;
}

export function formatDay(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export function formatBucket(seconds: number | null): string {
  if (seconds === null) return "Unavailable";
  return `${Math.floor(seconds / 60)}:${pad(seconds % 60)}`;
}

export const label = (value: string | null) => (value ? humanize(value) : "Unavailable");
export const risk = (value: number | null) => (value === null ? "Unavailable" : `${Math.round(value * 100)}%`);
