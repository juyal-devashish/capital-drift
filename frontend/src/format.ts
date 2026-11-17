// Formatting helpers: money, dates, counts and the names shown for warnings and statuses. Kept in one
// place so every screen speaks the same vocabulary.

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** "1 page" / "23 pages" */
export function plural(n: number, word: string, many = `${word}s`): string {
  return `${n.toLocaleString()} ${n === 1 ? word : many}`;
}

export function usd(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return `$${Math.round(v).toLocaleString("en-US")}`;
}

/** Compact dollars for chart labels: $12k, $1.2m. */
export function usdShort(v: number): string {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}m`;
  if (v >= 1e3) return `$${Math.round(v / 1e3)}k`;
  return `$${Math.round(v)}`;
}

export const WARNING_NAMES: Record<string, string> = {
  failing_early: "Failing early",
  overdue: "Past due",
  over_budget: "Over budget",
};

export const ITEM_STATUS_NAMES: Record<string, string> = {
  open: "Not yet checked",
  confirmed: "Confirmed",
  dismissed: "Dismissed",
  resolved: "Placed",
  resolved_by_rerun: "No longer raised",
};

export const KIND_NAMES: Record<string, string> = {
  condo_midrise: "Mid-rise condo",
  garden: "Garden apartments",
  sfh_hoa: "Single-family HOA",
};

/** A share as a percentage with one decimal: 0.933 -> 93.3%. */
export function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}
