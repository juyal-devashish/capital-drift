// Results: how well matching, warnings and review do on synthetic portfolios. The numbers come from one
// file written offline from the answer key (`python -m app.cli results`); the app never scores live.
import { api } from "../api";
import { EmptyState, Loading } from "../components/Marks";
import { pct } from "../format";
import { useAsync } from "../hooks";
import { usePageTitle } from "../prefs";
import { SyntheticNote } from "./Board";

const KIND_WORDS: Record<string, string> = { failing_early: "failing early", overdue: "past due", over_budget: "over budget" };

function kinds(by: Record<string, number>): string {
  const parts = Object.entries(by).map(([k, v]) => `${v} ${KIND_WORDS[k] ?? k}`);
  return parts.length ? parts.join(", ") : "none";
}

export function CapitalResults() {
  usePageTitle("Results");
  const r = useAsync(() => api.capital.results(), []);
  if (r.error)
    return (
      <EmptyState icon="chart" title="No results yet">
        {r.error}
      </EmptyState>
    );
  if (!r.data) return <Loading />;
  const d = r.data;
  const heldOut = d.held_out_seeds.join(", ");
  const match = d.matching.find((m) => m.seed === d.seed && m.labels === "rules + Claude");
  const rulesOnly = d.matching.find((m) => m.seed === d.seed && m.labels === "rules");
  const warn = d.warnings.find((w) => w.seed === d.seed && w.labels === "rules + Claude");
  const review = d.review.find((v) => v.seed === d.seed);
  const fc = d.forecast_backtest.find((b) => b.contributions === "flat" && b.group === "fresh");

  return (
    <>
      <header className="page-head with-actions">
        <div>
          <h1>How well it works</h1>
          <p className="lede">
            The data is made up, with problems planted on purpose, so each step can be scored against the right answers.
          </p>
        </div>
        <SyntheticNote />
      </header>

      <div className="stack">
        <section className="headline-grid" aria-label="Headline numbers">
          {match && (
            <div className="card headline">
              <span className="kpi-label">Invoices filed under the right part</span>
              <span className="big">{pct(match.component_accuracy)}</span>
              <p>Rules first, then Claude for the hard ones. Rules alone: {rulesOnly ? pct(rulesOnly.component_accuracy) : "–"}.</p>
            </div>
          )}
          {warn && (
            <div className="card headline">
              <span className="kpi-label">Planted problems caught</span>
              <span className="big">
                {warn.detected} of {warn.planted}
              </span>
              <p>Parts failing early, replacements put off, projects over budget.</p>
            </div>
          )}
          {review && (
            <div className="card headline">
              <span className="kpi-label">False alarms after a quick review</span>
              <span className="big">
                {review.before.false_alarms} → {review.after.false_alarms}
              </span>
              <p>A manager checked {review.invoices_reviewed} suggested invoices. Nothing real was lost.</p>
            </div>
          )}
          {fc && (
            <div className="card headline">
              <span className="kpi-label">Forecast: who ran out of money</span>
              <span className="big">
                {fc.called_and_ran_short} of {fc.ran_short}
              </span>
              <p>
                Called up to 5 years ahead, on data it had never seen. The reserve plan alone called {fc.plain_called_and_ran_short}.
              </p>
            </div>
          )}
        </section>

        <details className="more">
          <summary>Read these with care</summary>
          <div>
            <ul style={{ margin: 0 }}>
              {d.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        </details>

        <details className="more">
          <summary>See the full tables</summary>
          <div className="stack">
        <section className="stack">
          <div>
            <h2 style={{ marginBottom: "0.25rem" }}>1. Placing invoices against the reserve study</h2>
            <p className="quiet" style={{ margin: 0 }}>
              Rules first; on seed {d.seed}, Claude answered the invoices the rules left unsure ({d.claude_run.asked} asked: {d.claude_run.by_status.ok ?? 0}{" "}
              placed, {d.claude_run.by_status.unsure ?? 0} left unsure
              {Object.entries(d.claude_run.by_status)
                .filter(([k]) => k !== "ok" && k !== "unsure")
                .map(([k, v]) => `, ${v} ${k}`)
                .join("")}
              ). Accuracy counts unsure as wrong.
            </p>
          </div>
          <div className="table-wrap">
            <table className="ledger results-table">
              <thead>
                <tr>
                  <th>Seed</th>
                  <th>Matched by</th>
                  <th className="num">Decided</th>
                  <th className="num">Right part, all invoices</th>
                  <th className="num">Right when decided</th>
                  <th className="num">By dollars</th>
                  <th className="num">Wrong-fund flags</th>
                </tr>
              </thead>
              <tbody>
                {d.matching.map((m) => (
                  <tr key={`${m.seed}-${m.labels}`}>
                    <td>{m.seed}</td>
                    <td>{m.labels}</td>
                    <td className="num">{pct(m.coverage)}</td>
                    <td className="num">
                      <strong>{pct(m.component_accuracy)}</strong>
                    </td>
                    <td className="num">{pct(m.precision_on_decided)}</td>
                    <td className="num">{pct(m.dollar_weighted_accuracy)}</td>
                    <td className="num">
                      {m.wrong_fund_flags.flagged_correctly}/{m.wrong_fund_flags.true_wrong_fund_invoices}
                      {m.wrong_fund_flags.flagged_wrongly ? ` (${m.wrong_fund_flags.flagged_wrongly} wrong)` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="stack">
          <div>
            <h2 style={{ marginBottom: "0.25rem" }}>2. Repair-or-replace warnings against planted problems</h2>
            <p className="quiet" style={{ margin: 0 }}>
              "Perfect labels" feeds the detector the answer key's own matches, to show the detector alone. Each seed plants about 12 problems.
            </p>
          </div>
          <div className="table-wrap">
            <table className="ledger results-table">
              <thead>
                <tr>
                  <th>Seed</th>
                  <th>Matches</th>
                  <th className="num">Early failures</th>
                  <th className="num">Past due</th>
                  <th className="num">Over budget</th>
                  <th className="num">False alarms</th>
                </tr>
              </thead>
              <tbody>
                {d.warnings.map((w) => {
                  const e = w.events;
                  const cell = (k: string) => `${e[k].detected}/${e[k].planted}`;
                  return (
                    <tr key={`${w.seed}-${w.labels}`}>
                      <td>{w.seed}</td>
                      <td>{w.labels}</td>
                      <td className="num">
                        {cell("early_failure")}
                        {e.early_failure.median_delay_days !== null && <span className="sub">median {e.early_failure.median_delay_days} days</span>}
                      </td>
                      <td className="num">{cell("deferred")}</td>
                      <td className="num">{cell("cost_overrun")}</td>
                      <td className="num">
                        {w.false_alarms}
                        <span className="sub">{kinds(w.false_alarms_by_kind)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="quiet" style={{ margin: 0 }}>
            The detection threshold was fixed in advance from a simulated false-alarm rate. On seeds {heldOut}:{" "}
            {d.threshold_tradeoff
              .filter((t) => t.labels === "rules")
              .map((t) => `threshold ${t.threshold} catches ${t.caught}/${t.planted} early failures with ${t.false_failing_early} false ones`)
              .join("; ")}{" "}
            (rules-only matches; the default is 6).
          </p>
        </section>

        <section className="stack">
          <div>
            <h2 style={{ marginBottom: "0.25rem" }}>3. Forecast backtest: who ran short</h2>
            <p className="quiet" style={{ margin: 0 }}>
              Forecast from the end of 2020 using only invoices up to then (rules-only matches), compared with what followed in 2021–2025. The plain
              schedule assumes every planned replacement happens on time at plan cost. Seeds 14–17 were first run after the forecast was written.
            </p>
          </div>
          <div className="table-wrap">
            <table className="ledger results-table">
              <thead>
                <tr>
                  <th>Contributions</th>
                  <th>Seeds</th>
                  <th className="num">Ran short</th>
                  <th className="num">Forecast called</th>
                  <th className="num">Plain schedule called</th>
                  <th className="num">Band held the balance</th>
                </tr>
              </thead>
              <tbody>
                {d.forecast_backtest.map((b) => (
                  <tr key={`${b.contributions}-${b.group}`}>
                    <td>{b.contributions === "flat" ? "Flat" : "Rising with inflation"}</td>
                    <td>
                      {b.seeds.join(", ")}
                      <span className="sub">{b.group === "fresh" ? "fresh" : "used while building"}</span>
                    </td>
                    <td className="num">
                      {b.ran_short}
                      <span className="sub">{b.already_below_zero} already short in 2020</span>
                    </td>
                    <td className="num">
                      <strong>{b.called_and_ran_short}</strong>
                      <span className="sub">{b.false_calls} false</span>
                    </td>
                    <td className="num">
                      {b.plain_called_and_ran_short}
                      <span className="sub">{b.plain_false_calls} false</span>
                    </td>
                    <td className="num">
                      {Math.round(Math.min(...b.band_coverage) * 100)}–{Math.round(Math.max(...b.band_coverage) * 100)}%
                      <span className="sub">target 80%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="quiet" style={{ margin: 0 }}>
            Checked on seeds 7 and 11–13 with perfect labels: every missed call was an early failure with no warning by the end of 2020, and 4 of
            the 6 false calls were replacements planned but never done. The band reflects replacement cost alone, so it is too narrow.
          </p>
        </section>

        <section className="stack">
          <div>
            <h2 style={{ marginBottom: "0.25rem" }}>4. How much review clears the false alarms</h2>
            <p className="quiet" style={{ margin: 0 }}>
              A simulated property manager places only the candidate invoices listed beside each past-due warning, answering from the answer key.
              An upper bound: real people make mistakes.
            </p>
          </div>
          <div className="table-wrap">
            <table className="ledger results-table">
              <thead>
                <tr>
                  <th>Seed</th>
                  <th>Matches</th>
                  <th className="num">Invoices reviewed</th>
                  <th className="num">Unplaced invoices in queue</th>
                  <th className="num">False alarms before → after</th>
                  <th className="num">Problems caught</th>
                </tr>
              </thead>
              <tbody>
                {d.review.map((v) => (
                  <tr key={`${v.seed}-${v.labels}`}>
                    <td>{v.seed}</td>
                    <td>{v.labels}</td>
                    <td className="num">
                      <strong>{v.invoices_reviewed}</strong>
                    </td>
                    <td className="num">{v.unsure_in_queue}</td>
                    <td className="num">
                      {v.before.false_alarms} → <strong>{v.after.false_alarms}</strong>
                      <span className="sub">left: {kinds(v.after.false_alarms_by_kind)}</span>
                    </td>
                    <td className="num">
                      {v.after.detected}/{v.after.planted}
                      <span className="sub">{v.detections_lost.length ? `${v.detections_lost.length} lost` : "none lost"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
          </div>
        </details>
      </div>
    </>
  );
}
