import { RED_FLAGS } from "@/lib/console/flags";

/** snake_case to a readable label. */
export function humanize(value: string): string {
  const words = value.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const familyLabel = (family: string) => (family === "none" ? "Not a scam" : humanize(family));

export const flagLabel = (flag: string) => RED_FLAGS[flag as keyof typeof RED_FLAGS] ?? humanize(flag);

export const UNAVAILABLE = "Unavailable";

export function show(value: number | null, format: (value: number) => string = String): string {
  return value === null ? UNAVAILABLE : format(value);
}

export const ms = (value: number) => `${Math.round(value)} ms`;
export const rate = (value: number) => value.toFixed(1);
