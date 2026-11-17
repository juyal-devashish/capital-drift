// Help & guide: what the app does, what each role can do, how the warnings and the queue work, and
// what the colours and numbers mean.
import { Link } from "react-router-dom";
import { ROLE_NAMES, useAuth } from "../auth";
import { usePageTitle } from "../prefs";
import type { Role } from "../types";

const ROLE_DUTIES: Record<Role, string[]> = {
  board_member: ["Sees which associations are red and why", "Reads the review queue, its history and the forecast", "Cannot change anything"],
  property_manager: ["Works the review queue", "Confirms or dismisses warnings, with a comment", "Says which part of the plan an invoice paid for"],
  admin: ["Everything a property manager can do", "Rebuilds the whole queue after a data load"],
};

const SECTIONS = [
  ["what", "What it does"],
  ["roles", "Roles"],
  ["warnings", "The three warnings"],
  ["queue", "Working the queue"],
  ["colours", "Board colours"],
  ["forecast", "The forecast"],
  ["data", "About the data"],
] as const;

export function Help() {
  usePageTitle("Help & guide");
  const { user } = useAuth();
  return (
    <>
      <header className="page-head">
        <p className="eyebrow">Help</p>
        <h1>Help & guide</h1>
        <p className="lede">How the Capital Drift Monitor checks an association's spending against its reserve study.</p>
      </header>

      <div className="help-layout">
        <nav className="help-toc" aria-label="On this page">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`}>
              {label}
            </a>
          ))}
        </nav>
        <div className="help-body stack">
          <section id="what" className="panel">
            <h2>What it does</h2>
            <ol>
              <li>
                <strong>Places every invoice against the reserve study.</strong> Rules first; Claude answers the invoices the rules can't place;
                what neither can place goes to the review queue.
              </li>
              <li>
                <strong>Watches spending against the plan.</strong> Each part of the study is checked month by month, and a warning reads as a
                repair-or-replace call.
              </li>
              <li>
                <strong>Lets a property manager decide.</strong> Every decision is logged, and the warnings rerun as soon as an invoice is placed.
              </li>
              <li>
                <strong>Forecasts the reserve balance</strong> ten years ahead, so the board can see who runs short first.
              </li>
            </ol>
          </section>

          <section id="roles" className="panel">
            <h2>Roles</h2>
            <div className="grid-3">
              {(Object.keys(ROLE_DUTIES) as Role[]).map((r) => (
                <div key={r}>
                  <h3>
                    {ROLE_NAMES[r]} {user?.role === r && <span className="role-badge">You</span>}
                  </h3>
                  <ul>
                    {ROLE_DUTIES[r].map((d) => (
                      <li key={d}>{d}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>

          <section id="warnings" className="panel">
            <h2>The three warnings</h2>
            <ul>
              <li>
                <strong>Failing early:</strong> repairs are arriving much faster than usual for a part this age, and the plan doesn't replace it
                until more than a year out.
              </li>
              <li>
                <strong>Past due:</strong> the planned replacement year has passed and no completed replacement has been found.
              </li>
              <li>
                <strong>Over budget:</strong> a replacement has cost more than the plan's inflated cost plus a 15% contingency.
              </li>
            </ul>
          </section>

          <section id="queue" className="panel">
            <h2>Working the queue</h2>
            <p>
              Start with the past-due warnings. Each one lists <em>candidate invoices</em>: invoices from that association, big enough to be part
              of a replacement, that nobody could place or that went to the same kind of part in another building. Placing them correctly reruns
              the warnings at once, and the page shows what cleared. Confirm a warning that is real; dismiss one that isn't, with a comment for
              the board. A dismissal is never undone by a rerun.
            </p>
            <p>
              <Link to="/queue">Open the review queue</Link>
            </p>
          </section>

          <section id="colours" className="panel">
            <h2>Board colours</h2>
            <ul>
              <li>
                <strong>Red:</strong> a part failing early or past its planned replacement, either not yet checked or confirmed.
              </li>
              <li>
                <strong>Amber:</strong> a replacement over budget, or invoices not yet placed worth at least 10% of the yearly reserve
                contribution.
              </li>
              <li>
                <strong>Green:</strong> none of those. The colours track spending against the plan, not how well funded the reserve is; the
                forecast covers that.
              </li>
            </ul>
          </section>

          <section id="forecast" className="panel">
            <h2>The forecast</h2>
            <p>
              The reserve balance is replayed from the study's starting balance and then simulated ten years ahead over the study's replacement
              schedule. Past-due parts are due now, parts warned as failing early come due within three years, and replacement costs vary as much
              as this portfolio's finished projects did. The study doesn't say whether contributions rise, so both cases are shown. A balance below
              zero is a modelled shortfall: work that would need other money, or would be put off.
            </p>
          </section>

          <section id="data" className="panel">
            <h2>About the data</h2>
            <p>
              Everything here is synthetic: twenty made-up associations near Philadelphia, their reserve studies and ten years of invoices, with
              planted problems to find. <Link to="/results">The results page</Link> shows how well each step does against them.
            </p>
          </section>
        </div>
      </div>
    </>
  );
}
