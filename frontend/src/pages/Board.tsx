// Board view: every association, red first, with the main reasons in plain words, then who runs short
// of reserve money first. Read-only for everyone; the details sit behind "How is this worked out?".
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, STATIC } from "../api";
import { CAPITAL_DECIDE_ROLES, useAuth } from "../auth";
import { EmptyState, ErrorNote, Loading } from "../components/Marks";
import { KIND_NAMES, usd } from "../format";
import { useAsync } from "../hooks";
import { usePageTitle } from "../prefs";
import type { ForecastRow } from "../types";

const STATUS_WORDS = { red: "Needs attention", amber: "Watch", green: "On plan" } as const;
const UNCHECKED = " (not yet checked by the manager)";

export function SyntheticNote() {
  // The hosted snapshot already says so in its banner.
  return STATIC ? null : <span className="synthetic-note">Synthetic data</span>;
}

/** A reason without the "(not yet checked ...)" tail, which the card shows once as a tag instead. */
export function Reason({ text }: { text: string }) {
  const unchecked = text.endsWith(UNCHECKED);
  const confirmed = /\(confirmed by [^)]+\)$/.exec(text);
  const plain = unchecked ? text.slice(0, -UNCHECKED.length) : confirmed ? text.slice(0, confirmed.index).trim() : text;
  return (
    <li>
      {plain} {unchecked && <span className="tag-check">not checked yet</span>}
      {confirmed && <span className="tag-check">confirmed</span>}
    </li>
  );
}

function when(balance: number, year: number | null, share: number): string {
  if (balance < 0) return `Already short by ${usd(-balance)}`;
  if (year) return `Around ${year}`;
  return share > 0 ? `Probably not (${Math.round(share * 100)}% chance)` : "Not within 10 years";
}

function RunsShort() {
  const fc = useAsync(() => api.capital.forecast(), []);
  const [rising, setRising] = useState(false);
  if (fc.error) return <ErrorNote message={fc.error} onRetry={fc.reload} />;
  if (!fc.data) return <Loading />;
  const rows: ForecastRow[] = fc.data.associations;
  return (
    <section className="stack" style={{ marginTop: "2.5rem" }}>
      <div className="card-head" style={{ marginBottom: 0 }}>
        <div>
          <h2 style={{ marginBottom: "0.25rem" }}>Who runs out of reserve money first</h2>
          <p className="quiet" style={{ margin: 0 }}>
            A 10-year forecast of each association's reserve fund.
          </p>
        </div>
        <div className="chip-group" role="group" aria-label="Contributions">
          <button className={`chip${!rising ? " is-active" : ""}`} aria-pressed={!rising} onClick={() => setRising(false)}>
            Contributions stay flat
          </button>
          <button className={`chip${rising ? " is-active" : ""}`} aria-pressed={rising} onClick={() => setRising(true)}>
            Rise with inflation
          </button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="ledger compact">
          <thead>
            <tr>
              <th>Association</th>
              <th>Runs short</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.association_id}>
                <td>
                  <Link className="row-link" to={`/associations/${encodeURIComponent(r.association_id)}`}>
                    <span>
                      <i className={`light light-${r.status}`} aria-hidden="true" /> {r.name}
                    </span>
                  </Link>
                </td>
                <td>
                  {rising
                    ? when(r.start_balance_rising, r.first_short_year_rising, r.share_short_rising)
                    : when(r.start_balance, r.first_short_year, r.share_short)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="more">
        <summary>How is this worked out?</summary>
        <div>{fc.data.assumptions}</div>
      </details>
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
          <h1>Which associations need attention</h1>
          <p className="lede">Each association's spending, checked against its reserve plan. Click a card to see why.</p>
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
              <Link className="button" to="/queue">
                Open the review queue
              </Link>
            )}
          </div>
          <details className="more" style={{ marginTop: 0, marginBottom: "1.25rem" }}>
            <summary>What do the colours mean?</summary>
            <div>{b.rule}</div>
          </details>
          <div className="board-grid">
            {b.associations.map((a) => (
              <Link key={a.id} to={`/associations/${encodeURIComponent(a.id)}`} className={`card board-card is-${a.status}`}>
                <h3>
                  <i className={`light light-${a.status}`} aria-hidden="true" />
                  {a.name}
                </h3>
                <p className="sub">
                  {STATUS_WORDS[a.status]} · {KIND_NAMES[a.kind] ?? a.kind}, {a.town}
                </p>
                {a.reasons.length > 0 ? (
                  <ul>
                    {a.reasons.slice(0, 2).map((r) => (
                      <Reason key={r} text={r} />
                    ))}
                    {a.reasons.length > 2 && <li className="quiet">and {a.reasons.length - 2} more</li>}
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
