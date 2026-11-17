// API types. These mirror the Pydantic response models in backend/app/schemas.py.

export type Role = "board_member" | "property_manager" | "admin";

export interface Me {
  username: string;
  role: Role;
}

export type ItemStatus = "open" | "confirmed" | "dismissed" | "resolved" | "resolved_by_rerun";
export type WarningKind = "failing_early" | "overdue" | "over_budget";
export type BoardStatus = "red" | "amber" | "green";

export interface ReviewItem {
  id: string;
  kind: "warning" | "invoice";
  warning_kind: WarningKind | null;
  association_id: string;
  component_id: string | null;
  invoice_id: string | null;
  title: string;
  detail: string;
  amount_at_stake: number;
  opened_on: string;
  status: ItemStatus;
}

export interface ReviewItemPage {
  items: ReviewItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ReviewActionRow {
  id: number;
  action: string;
  comment: string | null;
  status_before: string | null;
  status_after: string;
  match_before: { label: string; component_id: string | null; method: string } | null;
  match_after: { label: string; component_id: string | null; method: string } | null;
  username: string;
  role: string;
  created_at: string;
}

export interface RelatedInvoice {
  id: string;
  invoice_date: string;
  vendor_name: string;
  memo: string;
  amount: number;
  fund_booked: string;
  label: string;
  component_id: string | null;
  method: string;
  role: "evidence" | "candidate";
}

export interface ReviewItemDetail extends ReviewItem {
  payload: { message?: string; numbers?: Record<string, number | string>; reasons?: string[] };
  invoices: RelatedInvoice[];
  actions: ReviewActionRow[];
}

export interface QueueChanges {
  opened: string[];
  reopened: string[];
  resolved_by_rerun: string[];
}

export interface ComponentInfo {
  id: string;
  association_id: string;
  category: string;
  name: string;
  location: string | null;
  useful_life_years: number;
  remaining_life_years: number;
  replacement_cost: number;
  planned_year: number;
}

export interface BoardAssociation {
  id: string;
  name: string;
  kind: string;
  town: string;
  units: number;
  status: BoardStatus;
  reasons: string[];
  open_warnings: number;
  confirmed_warnings: number;
  unplaced_invoices: number;
  unplaced_amount: number;
}

export interface Board {
  synced: boolean;
  rule: string;
  associations: BoardAssociation[];
}

export interface YearRow {
  year: number;
  planned: number;
  replacements: number;
  repairs: number;
  routine: number;
  unplaced: number;
}

export interface PartRow {
  component_id: string;
  name: string;
  location: string | null;
  useful_life_years: number;
  replacement_cost: number;
  planned_years: number[];
  replacement_spend_by_year: Record<string, number>;
  repair_spend: number;
}

export interface ForecastYear {
  year: number;
  p10: number;
  p50: number;
  p90: number;
  share_below_zero: number;
}

export interface ForecastData {
  association_id: string;
  as_of: number;
  start_balance: number;
  history: { year: number; contributions: number; reserve_spend: number; balance: number }[];
  years: ForecastYear[];
  share_short: number;
  first_short_year: number | null;
  due: Record<string, number>;
}

export interface ForecastRow {
  association_id: string;
  name: string;
  status: BoardStatus;
  start_balance: number;
  annual_contribution: number;
  share_short: number;
  first_short_year: number | null;
  lowest_p50_in_contributions: number;
  start_balance_rising: number;
  share_short_rising: number;
  first_short_year_rising: number | null;
}

export interface ForecastBoard {
  as_of: number | null;
  assumptions: string;
  associations: ForecastRow[];
}

export interface AssociationTimeline {
  id: string;
  name: string;
  kind: string;
  town: string;
  units: number;
  buildings: number;
  study_year: number;
  inflation_rate: number;
  annual_contribution: number;
  reserve_balance_start: number;
  status: BoardAssociation;
  years: YearRow[];
  parts: PartRow[];
  warnings: ReviewItem[];
  forecast: ForecastData | null;
  forecast_rising: ForecastData | null;
  forecast_assumptions: string;
}

/** Offline evaluation bundle (synthetic data), see backend/app/evals/bundle.py. */
export interface CapitalResults {
  label: string;
  generated_on: string;
  seed: number;
  held_out_seeds: number[];
  caveats: string[];
  matching: {
    seed: number;
    labels: string;
    invoices: number;
    coverage: number;
    component_accuracy: number;
    precision_on_decided: number;
    dollar_weighted_accuracy: number;
    repairs: number;
    replacements: number;
    wrong_fund_flags: { true_wrong_fund_invoices: number; flagged_correctly: number; flagged_wrongly: number; recall: number };
  }[];
  claude_run: { asked: number; from_cache: number; by_status: Record<string, number>; input_tokens: number; output_tokens: number; cache_read_tokens: number };
  warnings: {
    seed: number;
    labels: string;
    events: Record<string, { planted: number; detected: number; median_delay_days: number | null; warned_before_replacement?: number; replaced_in_history?: number }>;
    detected: number;
    planted: number;
    false_alarms: number;
    false_alarms_by_kind: Record<string, number>;
    per_100: number;
  }[];
  threshold_tradeoff: { threshold: number; labels: string; caught: number; planted: number; false_failing_early: number }[];
  forecast_backtest: {
    contributions: string;
    seeds: number[];
    group: string;
    ran_short: number;
    already_below_zero: number;
    called_and_ran_short: number;
    false_calls: number;
    plain_called_and_ran_short: number;
    plain_false_calls: number;
    band_coverage: number[];
    final_year_coverage: number[];
  }[];
  review: {
    seed: number;
    labels: string;
    invoices_reviewed: number;
    unsure_in_queue: number;
    before: { false_alarms: number; detected: number; planted: number };
    after: { false_alarms: number; detected: number; planted: number; false_alarms_by_kind: Record<string, number> };
    detections_lost: string[];
  }[];
}
