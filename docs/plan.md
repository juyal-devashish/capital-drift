# Plan

**What it is:** a tool that checks whether a building's money is going where its repair plan said it would. It sorts invoices to building parts, warns when spending drifts from the plan, and lets a person review the warnings. All data is made up.

## Defaults

These are my recommendations. Change any of them before the step that uses it.

- **Data:** 20 made-up Philadelphia-area associations in 3 kinds (mid-rise condo, garden apartments, single-family HOA), 10 years of invoices (2016–2025) and a 10-year forecast.
- **Invoices:** about 3,500 with messy vendor names and memos. With seed 7: 57% routine services, 36% repairs to a building part, 7% replacement projects, and about 4% of all invoices flagged as ambiguous.
- **Answer key:** about 15 planted problems (early failures, cost overruns, deferred work, miscoded spend), kept out of the app's database.
- **AI:** rules first, Claude on Amazon Bedrock for the rest. Tests never call it. Ask before any live run.
- **Users:** board member (read-only summary), property manager (works the review queue), admin.
- **Stack:** Tick & Tie's runtime (FastAPI, LangGraph, React) on Postgres, deployed on AWS.

## Week 1: a demo you can send

Three changes come from FiXA's own site (fixai.tech, read on 2026-11-16). Its HOA page says plans live in long reports nobody searches, the finances sit in another system, and spending is hard to line up against the plan. Its property-manager page says repair-or-replace decisions get made without data. Steps marked ★ answer those points.

| Day | Step | Done when |
| --- | --- | --- |
| 1 ✅ | Data model and fake-data generator | Tables migrate on Postgres. The generator makes the 20 associations, invoices and answer key. Tests pass. |
| 2 ★ ✅ | Reserve studies as PDFs | The generator also writes each association's reserve study as a PDF report. The app reads the components back from the PDF using Tick & Tie's table parser, and the result matches the CSV exactly. |
| 3 ✅ | Invoice sorting with rules | Each invoice is marked upkeep, a building part, or unsure. Accuracy is scored against the answer key. |
| 4 ✅ | AI sorting for the leftovers | Claude handles the unsure ones (stubbed in tests). Before/after accuracy and cost are reported. |
| 5 ★ | Repair-or-replace warnings | Each building part's spend is checked against plan over time. A warning reads as a repair-or-replace call, for example: "repairs on this boiler now cost more each year than replacing it would; consider moving the replacement up." It reports how early the warnings fire and how many are false alarms. |
| 6 ★ | Review queue and roles | Warnings and unsure matches land in Tick & Tie's queue. Property managers decide; every decision is logged. Roles become board member, property manager and admin. |
| 7–8 ★ | Screens | A board view (read-only: which associations are red, and why, in plain words) and a manager view (the queue, the association timeline of plan vs. actual with warnings), plus a results page. |

## Week 2: polish (optional)

1. ✅ A forecast of which associations run out of reserve money first (done 2026-11-17; see [results.md](results.md)).
2. Deploy on AWS. Only with your go-ahead. App Runner closed to new customers on 2026-04-30, so the plan now uses ECS Express Mode (Fargate), RDS, and S3 with CloudFront; Bedrock isn't needed at run time. Options, costs and decisions are in [deploy-plan.md](deploy-plan.md).
3. A 2-minute walkthrough recording and a short message to FiXA's founders.

## Rules

- Make one commit per step, and run `make test` and `make lint` before each.
- Use only made-up data, labelled as made up wherever it appears.
- The repo is public, so commit nothing private. Nothing deploys until you say so.
- Keep the credit to Shreyash at the top of the README.

## Settled

- Days 7–8 done on 2026-11-17:
  - **Board view:** read-only. Every association is red, amber or green, with its reasons in plain words, and it says whether a manager has checked each warning. The colour rule is stated on the page.
  - **Manager queue:** past-due warnings come first, with their candidate invoices. Placing one reruns the warnings and shows what cleared.
  - **Association page:** plan against actual per year, with its warnings and parts.
  - **Results page:** shows an offline results file written from the answer key, which the app itself never loads.
  - **Roles:** board members and property managers see only the capital screens, and the brand reads "Capital Drift, built on Tick & Tie".
  - **Browser check:** done as each role on a copy of the seed 7 data. Placing contract 6896's two invoices on the Bldg A boiler cleared both its false past-due warning and the Bldg B over-budget warning.
  - **Caveat on that check:** I picked contract 6896 because the answer key says it's Bldg A's. On screen, both contracts' memos say Bldg B, so a real manager would have to check the contract itself. That's a concrete case of why the review numbers are an upper bound.
  - **Board split on seed 7:** 8 red, 10 amber, 2 green. 6 of the ambers come only from the unplaced-invoice rule, whose 10%-of-contribution threshold is a round number, not a tested one.
- Day 6 done on 2026-11-17: the review queue (warnings and unsure invoices) with board member (read-only), property manager and admin roles, decisions that survive reruns, and an append-only log. Simulated review of only the invoices listed beside overdue warnings cleared every false overdue and over-budget warning on all seeds without losing a detection: on held-out seed 12, 13 invoices took false alarms from 10 to 2. Kept beside Tick & Tie's exception queue rather than inside it, since that one is tied to document sets. The new roles sit alongside Tick & Tie's analyst, controller and auditor roles instead of replacing them, so its financial QA screens keep working. Details in [results.md](results.md).
- Day 5 done on 2026-11-17: repair-or-replace warnings (failing early, overdue, over budget) replayed month by month with no lookahead. On held-out seeds with perfect labels, they caught all deferred and over-budget replacements and 12 of 15 early failures, each before the emergency replacement, about 14–15 months after onset. Rules-only matching adds false overdue warnings where replacement invoices stay unsure, which Claude cuts on seed 7 from 12 false alarms to 4. Details in [results.md](results.md).
- Day 4 done on 2026-11-16: Claude Opus 5.5 answers the invoices the rules leave unsure. On seed 7, rules + Claude reach 93.3% component accuracy (rules alone 86.7%) and catch all 80 wrong-fund invoices, for $1.22 of API calls. Details in [results.md](results.md).
- Day 3 done on 2026-11-16: rules decide 87-89% of invoices and are right on about 98% of those; 85-88% component accuracy over all invoices on held-out seeds. Results and caveats are in [results.md](results.md).
- Day 2 done on 2026-11-16: each association's reserve study is also a 3-page PDF report (cover with funding summary, component inventory, replacement schedule). The app loads components and funding figures from the PDFs by default. All 300 studies across seeds 1-15 read back exactly. A row it can't read is a warning, and the loader refuses a study with any warning.
- Day 1 done on 2026-11-16: tables migrate on SQLite and Postgres 17. `python -m app.cli synth` writes and loads the data. Loading twice replaces rather than duplicates.

- Tick & Tie is separate from the user's Tech Observer work (confirmed on 2026-11-16).
