# Plan: from Tick & Tie to Capital Drift Monitor

Tick & Tie reconciles the same figure across several documents at one point in time. This project reconciles **planned capital spend** (from a reserve study) against **actual spend** (from invoices) **over time**, per component. The agent runtime, review flow and audit trail carry over. The domain layer is new.

## Keep (change little or nothing)

| Area | Files | Notes |
| --- | --- | --- |
| Agent runtime | `agents/graph.py`, `agents/runner.py`, `agents/state.py` | Supervisor graph, checkpoints, thread-pool runner. Node list changes. |
| Tool executor | `agents/tools.py` (executor part) | Validated JSON-schema tools, retries, per-call trace rows. Tool definitions change. |
| LLM wrapper | `agents/llm.py` | Budgeted calls with a cache. Repurpose from label mapping to invoice matching. |
| Core | `core/config.py`, `core/logging.py`, `core/security.py` | Rename the `FINQA_` env prefix. |
| DB plumbing | `db/session.py`, `db/migrate.py`, Alembic | Switch the default to Postgres. |
| Run, trace and review tables | `Run`, `RunStep`, `ToolCall`, `ExceptionRecord`, `ReviewDecision`, `AppSetting` | Rename `ExceptionRecord` to a general finding with kinds: low-confidence match, drift alert, unmatched invoice. |
| Review UI shell | `Layout`, `Queue`, `DecisionPanel`, `AuditLog`, `RunView`, `Runs`, `Login`, `Users`, `Toast`, `CommandPalette` | Restyle and relabel. |

## Replace

| Tick & Tie | Becomes |
| --- | --- |
| `Company`, `DocumentSet`, `Document`, `LineItem`, `HistoricalBaseline`, `LabelMapping` | `Portfolio`, `Association`, `ReserveComponent` (category, useful life, replacement cost, planned year, remaining life), `Invoice` (vendor, date, amount, memo), `InvoiceMatch` (component, confidence, method, evidence) |
| `parsers/` (PDF and XLSX figure tables) | CSV and XLSX loaders for reserve studies and invoice exports |
| `domain/reconcile.py`, `units.py`, `periods.py`, `vocabulary.py` | `domain/matching.py` (rules: vendor trade, keywords, location), `domain/drift.py`, `domain/forecast.py` |
| Agent nodes: extraction → reconciliation → baseline → exceptions | ingest → match (rules, then LLM for the rest) → drift → forecast → findings |
| Pages: `Companies`, `CompanyView`, `Sets`, `SetView`, `Upload`, `Reports`, `Rules`, `Overview` | Portfolio overview, association view (component timeline), invoice upload, capital forecast |
| `TickTieStrip`, `EvidenceViewer` | Match evidence card (invoice text next to the component) |

## New

1. **Synthetic data generator.** It builds reserve studies for about 20 associations and about 3,000 invoices with messy memos, plus planted ground truth: true component per invoice and components with injected early failure. The ground truth stays out of the app database, the same rule Tick & Tie follows.
2. **Drift detection.** A per-component sequential test (CUSUM or a sequential likelihood ratio) on spend relative to plan, with an alert time and an estimated shift. It draws on the user's change-detection research and Micron drift monitoring.
3. **Forecast.** Reserve balance by year with uncertainty bands, plus a backtest against a naive baseline.
4. **Eval.** Match accuracy (top-1, and by method), drift detection delay and false alarms, cost per 1,000 invoices. Report it per split, with the synthetic-data caveat.
5. **AWS deploy.** RDS Postgres plus App Runner or Lambda for the API, the UI on S3 and CloudFront, Bedrock for the LLM. Only with the user's go-ahead.

## Order of work

1. Data model and Alembic migration, then the synthetic generator with tests.
2. Rules matcher and eval, then the LLM matcher for the rest.
3. Drift detection and its eval.
4. Rework the agent graph and findings around the new nodes.
5. UI: association timeline, findings queue, portfolio overview.
6. Forecast panel.
7. Deploy on AWS, then a 2-minute walkthrough recording.

## Open questions

- ~~Did any Tick & Tie code come from the user's Tech Observer work?~~ **Settled on 2026-11-16:** the user confirmed it's separate from their Tech Observer work, so nothing here is employer code.
- Should the project keep Tick & Tie's auth roles (analyst, controller, auditor, admin), or switch to board member, property manager and admin?
