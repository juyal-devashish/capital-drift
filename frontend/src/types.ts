// API types. These mirror the Pydantic response models in backend/app/schemas.py.

export type Role = "analyst" | "controller" | "auditor" | "admin" | "board_member" | "property_manager";
export type Severity = "high" | "medium" | "low";
export type ExceptionStatus = "open" | "accepted" | "rejected" | "overridden" | "resolved_by_rerun";
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type DecisionAction = "accept" | "reject" | "override" | "comment" | "reopen";

export interface Me {
  username: string;
  role: Role;
}

export interface Company {
  id: string;
  name: string;
  sector: string | null;
  currency: string;
  fiscal_year_end: string | null;
  segments: string[];
}

export interface CompanyInput {
  id: string;
  name: string;
  sector?: string;
  currency: string;
  fiscal_year_end?: string;
  segments: string[];
}

export interface RunBrief {
  id: string;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  step_count: number;
  current_node: string | null;
}

export interface SetSummary {
  id: string;
  company_id: string;
  company_name: string;
  currency: string;
  fiscal_year: number;
  source: string;
  documents: number;
  latest_run: RunBrief | null;
  open_exceptions: number;
  total_exceptions: number;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  format: "pdf" | "xlsx" | "csv";
  size_bytes: number;
  pages: number | null;
  sha256: string;
}

export interface SetDetail extends SetSummary {
  document_list: DocumentInfo[];
}

export interface RunStep {
  seq: number;
  node: string;
  started_at: string;
  duration_ms: number;
  summary: Record<string, unknown>;
}

export interface Run {
  id: string;
  set_id: string;
  status: RunStatus;
  current_node: string | null;
  step_count: number;
  created_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  stats: Record<string, any>;
}

export interface RunDetail extends Run {
  steps: RunStep[];
}

export interface ToolCall {
  id: number;
  node: string;
  tool: string;
  input: Record<string, unknown>;
  output_summary: Record<string, unknown> | null;
  status: "ok" | "error";
  attempts: number;
  duration_ms: number;
  error: string | null;
  created_at: string;
}

/** Where a figure sits in its source document. Which keys exist depends on the file type. */
export interface Location {
  doc: string;
  page?: number;
  table?: string;
  bbox?: [number, number, number, number];
  page_size?: [number, number];
  sheet?: string;
  cell?: string;
  line?: number;
  row?: string;
  column?: string;
}

export interface EvidenceItem {
  line_item_id: number;
  document_id: string;
  filename: string;
  value: number | null;
  displayed: string;
  location: Location;
  missing: boolean;
}

export interface ExceptionItem {
  id: string;
  set_id: string;
  metric: string;
  period: string;
  type: string;
  severity: Severity;
  status: ExceptionStatus;
  expected_value: number | null;
  reported_value: number | null;
  override_value: number | null;
  unit: string;
  outlier_documents: string[];
  explanation: string;
  created_at: string;
  updated_at: string;
}

export interface Decision {
  id: number;
  action: DecisionAction;
  comment: string | null;
  override_value: number | null;
  status_before: ExceptionStatus;
  status_after: ExceptionStatus;
  username: string;
  role: Role;
  created_at: string;
}

export interface ExceptionDetail extends ExceptionItem {
  evidence: {
    supporting: EvidenceItem[];
    conflicting: EvidenceItem[];
    baseline: { period: string; value: number; source?: string } | null;
    detail: Record<string, unknown>;
  };
  decisions: Decision[];
  documents: Record<string, string>;
}

export interface ExceptionPage {
  items: ExceptionItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface Summary {
  sets: number;
  runs_by_status: Record<string, number>;
  exceptions_by_status: Record<string, number>;
  open_by_severity: Record<string, number>;
  open_by_type: Record<string, number>;
}

export interface Rules {
  anomaly_threshold: number;
  baseline_metrics: string[];
}

export interface AuditEntry {
  id: number;
  exception_id: string;
  set_id: string;
  metric: string;
  period: string;
  severity: Severity;
  unit: string;
  action: DecisionAction;
  comment: string | null;
  override_value: number | null;
  status_before: ExceptionStatus;
  status_after: ExceptionStatus;
  username: string;
  role: Role;
  created_at: string;
}

export interface AuditPage {
  items: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface CompanyReport {
  company_id: string;
  company_name: string;
  sets: number;
  open: number;
  high: number;
  decided: number;
}

export interface Reports {
  by_company: CompanyReport[];
  type_by_severity: Record<string, Partial<Record<Severity, number>>>;
  by_metric: Record<string, number>;
  decisions_by_user: Record<string, number>;
  decisions_by_action: Record<string, number>;
}

export interface UserInfo {
  username: string;
  role: Role;
  decisions: number;
  runs_started: number;
  last_active: string | null;
}

export interface SystemStatus {
  version: string;
  database: string;
  llm_enabled: boolean;
  llm_model: string | null;
  llm_max_calls_per_run: number;
  worker_threads: number;
  max_steps: number;
  anomaly_threshold: number;
  counts: Record<string, number>;
  runs_by_status: Record<string, number>;
}

export interface ToolSchema {
  name: string;
  description: string;
  [key: string]: unknown;
}

// ------------------------------------------------------------------ capital planning (Capital Drift)
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
