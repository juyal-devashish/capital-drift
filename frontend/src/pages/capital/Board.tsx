// Board view: every association, red first, with the reasons in plain words. Read-only for everyone;
// each warning says whether a property manager has checked it yet.
import { Link } from "react-router-dom";
import { api } from "../../api";
import { CAPITAL_DECIDE_ROLES, useAuth } from "../../auth";
import { EmptyState, ErrorNote, Loading } from "../../components/Marks";
import { KIND_NAMES, plural, usd } from "../../format";
import type { ForecastRow } from "../../types";
import { useAsync } from "../../hooks";
import { usePageTitle } from "../../prefs";

const STATUS_WORDS = { red: "Needs attention", amber: "Watch", green: "On plan" } as const;

export function SyntheticNote() {
  return <span className="synthetic-note">Synthetic data: made-up associations, studies and invoices</span>;
}

function when(balance: number, year: number | null, share: number): string {
  if (balance < 0) return `Already short ${usd(-balance)}`;
  if (year) return `${year} (${Math.round(share * 100)}% of runs)`;
  return share > 0 ? `Not in the middle case (${Math.round(share * 100)}% of runs)` : "Not within ten years";
}

function RunsShort() {
  const fc = useAsync(() => api.capital.forecast(), []);
  if (fc.error) return <ErrorNote message={fc.error} onRetry={fc.reload} />;
  if (!fc.data) return <Loading />;
  const rows: ForecastRow[] = fc.data.associations;
  return (
    <section className="stack" style={{ marginTop: "2rem" }}>
      <div>
        <h2 style={{ marginBottom: "0.25rem" }}>Who runs short of reserve money first</h2>
        <p className="quiet" style={{ margin: 0 }}>
          A ten-year forecast from the end of {fc.data.as_of}. The study doesn't say whether contributions rise, so both cases are shown.{" "}
          {fc.data.assumptions}
        </p>
      </div>
      <div className="table-wrap">
        <table className="ledger compact">
          <thead>
            <tr>
              <th>Association</th>
              <th>Flat contributions: short in</th>
              <th>Rising with inflation: short in</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.association_id}>
                <td>
                  <Link className="row-link" to={`/capital/associations/${encodeURIComponent(r.association_id)}`}>
                    <span>
                      <i className={`light light-${r.status}`} aria-hidden="true" /> {r.name}
                    </span>
                  </Link>
                </td>
                <td>{when(r.start_balance, r.first_short_year, r.share_short)}</td>
                <td>{when(r.start_balance_rising, r.first_short_year_rising, r.share_short_rising)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Board() {
  usePageTitle("Board view");
  const { can } = useAuth();
  const board = useAsync(() => api.capital.board(), []);
  if (board.error) return <ErrorNote message={board.error} onRetry={board.reload} />;
  if (!board.data) return <Loading />;
  const b = board.data;
  const count = (s: string) => b.associations.filter((a) => a.status === s).length;

  return (
    <>
      <header className="page-head with-actions">
        <div>
          <p className="eyebrow">Capital planning</p>
          <h1>Which associations need attention</h1>
          <p className="lede">Each association's spending checked against its reserve study, with the reasons in plain words.</p>
        </div>
        <SyntheticNote />
      </header>

      {!b.synced ? (
        <EmptyState icon="alert" title="The review queue hasn't been built yet">
          Until it has, every association would read green. An admin can build it from the review queue page.
        </EmptyState>
      ) : (
        <>
          <div className="board-summary" aria-label="Summary">
            <span>
              <i className="light light-red" aria-hidden="true" /> {count("red")} need attention
            </span>
            <span>
              <i className="light light-amber" aria-hidden="true" /> {count("amber")} to watch
            </span>
            <span>
              <i className="light light-green" aria-hidden="true" /> {count("green")} on plan
            </span>
            {can(...CAPITAL_DECIDE_ROLES) && (
              <Link className="button" to="/capital/queue">
                Open the review queue
              </Link>
            )}
          </div>
          <p className="rule-note">
            <strong>How the colours are set.</strong> {b.rule}
          </p>
          <div className="board-grid">
            {b.associations.map((a) => (
              <Link key={a.id} to={`/capital/associations/${encodeURIComponent(a.id)}`} className={`card board-card is-${a.status}`}>
                <h3>
                  <i className={`light light-${a.status}`} aria-hidden="true" />
                  {a.name}
                </h3>
                <p className="sub">
                  {STATUS_WORDS[a.status]} · {KIND_NAMES[a.kind] ?? a.kind}, {a.town} · {plural(a.units, "unit")}
                </p>
                {a.reasons.length > 0 ? (
                  <ul>
                    {a.reasons.slice(0, 4).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                    {a.reasons.length > 4 && <li className="quiet">and {a.reasons.length - 4} more</li>}
                  </ul>
                ) : (
                  <p className="sub">Spending matches the plan so far.</p>
                )}
              </Link>
            ))}
          </div>
          <RunsShort />
        </>
      )}
    </>
  );
}
