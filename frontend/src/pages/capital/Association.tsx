// One association: plan against actual year by year (the study's replacement cycles, inflated, next to
// the replacement and repair spend found in its invoices), the warnings on the timeline, and every part.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { ErrorNote, Loading } from "../../components/Marks";
import { KIND_NAMES, plural, usd, usdShort } from "../../format";
import { useAsync } from "../../hooks";
import { usePageTitle } from "../../prefs";
import type { AssociationTimeline, ForecastData, ReviewItem } from "../../types";
import { ForecastChart } from "./ForecastChart";
import { SyntheticNote } from "./Board";
import { ItemStatus, ItemTag } from "./Queue";

const COUNTED = ["open", "confirmed"];

function Timeline({ a }: { a: AssociationTimeline }) {
  const max = Math.max(1, ...a.years.map((y) => Math.max(y.planned, y.replacements, y.repairs)));
  const flagsByYear = new Map<number, ReviewItem[]>();
  a.warnings.forEach((w) => {
    const y = Number(w.opened_on.slice(0, 4));
    flagsByYear.set(y, [...(flagsByYear.get(y) ?? []), w]);
  });
  const h = (v: number) => `${Math.max((v / max) * 100, v > 0 ? 1.5 : 0)}%`;
  return (
    <section className="panel">
      <h2>Plan against actual</h2>
      <p className="quiet" style={{ marginTop: 0 }}>
        Grey: replacements the study planned that year (inflated). Blue: replacement spend found. Amber: repair spend. Dots: warnings
        raised that year.
      </p>
      <div className="timeline" style={{ ["--cols" as string]: a.years.length }} role="img" aria-label="Planned and actual capital spend per year">
        {a.years.map((y) => (
          <div
            key={y.year}
            className="tl-year"
            title={`${y.year}: planned ${usd(y.planned)}, replacements ${usd(y.replacements)}, repairs ${usd(y.repairs)}, unplaced ${usd(y.unplaced)}`}
          >
            <div className="tl-bars">
              <span className="tl-planned" style={{ height: h(y.planned) }} />
              <span className="tl-replacements" style={{ height: h(y.replacements) }} />
              <span className="tl-repairs" style={{ height: h(y.repairs) }} />
            </div>
            <span className="tl-label">{y.year}</span>
            <span className="tl-flags">
              {(flagsByYear.get(y.year) ?? []).map((w) => (
                <Link
                  key={w.id}
                  to={`/capital/queue/${encodeURIComponent(w.id)}`}
                  title={w.title}
                  className={`tl-flag${w.warning_kind === "over_budget" ? " is-amber" : ""}${COUNTED.includes(w.status) ? "" : " is-off"}`}
                  aria-label={w.title}
                />
              ))}
            </span>
          </div>
        ))}
      </div>
      <div className="legend">
        <span>
          <i className="tl-planned" /> Planned
        </span>
        <span>
          <i className="tl-replacements" /> Replacements found
        </span>
        <span>
          <i className="tl-repairs" /> Repairs
        </span>
        <span>Tallest bar: {usdShort(max)}</span>
      </div>
    </section>
  );
}

/** One sentence a board member can repeat: where the reserve stands and when it runs short, if it does. */
export function forecastSentence(f: ForecastData, contribution: string): string {
  const now = f.start_balance < 0 ? `a modelled shortfall of ${usd(-f.start_balance)}` : `${usd(f.start_balance)} in reserve`;
  const runs = Math.round(f.share_short * 100);
  const when =
    f.start_balance < 0
      ? "It is already short."
      : f.first_short_year
        ? `In the middle case it runs short in ${f.first_short_year}; ${runs}% of runs go short within ten years.`
        : runs > 0
          ? `In the middle case it stays above zero, but ${runs}% of runs go short within ten years.`
          : "It stays above zero in every run.";
  return `With ${contribution}, the books end ${f.as_of} at ${now}. ${when}`;
}

function ForecastPanel({ a }: { a: AssociationTimeline }) {
  const [mode, setMode] = useState<"flat" | "rising">("flat");
  const f = mode === "flat" ? a.forecast : a.forecast_rising;
  if (!f) return null;
  const words = mode === "flat" ? "flat contributions" : "contributions rising with inflation";
  return (
    <section className="panel">
      <div className="card-head">
        <h2>Reserve balance forecast</h2>
        <div className="chip-group" role="group" aria-label="Contributions">
          {(["flat", "rising"] as const).map((m) => (
            <button key={m} className={`chip${mode === m ? " is-active" : ""}`} aria-pressed={mode === m} onClick={() => setMode(m)}>
              {m === "flat" ? "Flat contributions" : "Rising with inflation"}
            </button>
          ))}
        </div>
      </div>
      <p style={{ marginTop: 0 }}>{forecastSentence(f, words)}</p>
      <ForecastChart f={f} />
      <div className="legend">
        <span>
          <i className="lg-history" /> Balance so far (study start + contributions − replacements found)
        </span>
        <span>
          <i className="lg-median" /> Middle case
        </span>
        <span>
          <i className="lg-band" /> 10th–90th percentile, from replacement cost alone
        </span>
        <span>
          <i className="lg-short" /> Below zero: a modelled shortfall
        </span>
      </div>
      <p className="quiet" style={{ fontSize: "var(--t-sm)", marginBottom: 0 }}>
        {a.forecast_assumptions} <Link to="/capital/results">How well this did in a backtest</Link>.
      </p>
    </section>
  );
}

export function CapitalAssociation() {
  const { id = "" } = useParams();
  const data = useAsync(() => api.capital.association(id), [id]);
  usePageTitle(data.data?.name ?? "Association");
  if (data.error) return <ErrorNote message={data.error} onRetry={data.reload} />;
  if (!data.data) return <Loading />;
  const a = data.data;
  const s = a.status;
  const totals = a.years.reduce(
    (t, y) => ({ planned: t.planned + y.planned, replacements: t.replacements + y.replacements, repairs: t.repairs + y.repairs, unplaced: t.unplaced + y.unplaced }),
    { planned: 0, replacements: 0, repairs: 0, unplaced: 0 },
  );

  return (
    <>
      <header className="page-head with-actions">
        <div>
          <p className="eyebrow">
            <Link to="/capital">Board view</Link> · {a.id}
          </p>
          <h1>
            <i className={`light light-${s.status}`} aria-hidden="true" /> {a.name}
          </h1>
          <p className="lede">
            {KIND_NAMES[a.kind] ?? a.kind} in {a.town}, {plural(a.units, "unit")} in {plural(a.buildings, "building")}. Reserve study from{" "}
            {a.study_year}, assuming {(a.inflation_rate * 100).toFixed(1)}% cost inflation a year; {usd(a.annual_contribution)} a year goes into reserves.
          </p>
        </div>
        <SyntheticNote />
      </header>

      <div className="stack">
        {s.reasons.length > 0 && (
          <section className="panel">
            <h2>Why it's {s.status}</h2>
            <ul style={{ margin: 0 }}>
              {s.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </section>
        )}

        <div className="kpis">
          <div className="kpi">
            <span className="kpi-label">Replacements planned</span>
            <span className="kpi-value">{usdShort(totals.planned)}</span>
            <span className="kpi-hint">in the years shown</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Replacements found</span>
            <span className="kpi-value">{usdShort(totals.replacements)}</span>
            <span className="kpi-hint">invoices placed as replacements</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Repairs</span>
            <span className="kpi-value">{usdShort(totals.repairs)}</span>
            <span className="kpi-hint">to reserve parts</span>
          </div>
          <div className={`kpi${totals.unplaced ? " kpi-ochre" : ""}`}>
            <span className="kpi-label">Not yet placed</span>
            <span className="kpi-value">{usdShort(totals.unplaced)}</span>
            <span className="kpi-hint">
              <Link to={`/capital/queue?kind=invoice&association_id=${encodeURIComponent(a.id)}`}>See the invoices</Link>
            </span>
          </div>
        </div>

        <Timeline a={a} />

        <ForecastPanel a={a} />

        {a.warnings.length > 0 && (
          <section className="stack">
            <h2 style={{ margin: 0 }}>Warnings</h2>
            <div className="table-wrap">
              <table className="ledger">
                <tbody>
                  {a.warnings.map((w) => (
                    <tr key={w.id}>
                      <td className="title-cell">
                        <Link className="row-link" to={`/capital/queue/${encodeURIComponent(w.id)}`}>
                          {w.title}
                          <small>
                            <ItemTag item={w} />
                          </small>
                        </Link>
                      </td>
                      <td className="nowrap">{w.opened_on}</td>
                      <td>
                        <ItemStatus status={w.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section className="stack">
          <h2 style={{ margin: 0 }}>The reserve study's parts</h2>
          <div className="table-wrap">
            <table className="ledger compact">
              <thead>
                <tr>
                  <th>Part</th>
                  <th className="num">Life</th>
                  <th className="num">Cost (study)</th>
                  <th>Planned in</th>
                  <th>Replacement spend found</th>
                  <th className="num">Repairs</th>
                </tr>
              </thead>
              <tbody>
                {a.parts.map((p) => {
                  const found = Object.entries(p.replacement_spend_by_year);
                  return (
                    <tr key={p.component_id}>
                      <td>
                        {p.name}
                        {p.location ? ` (${p.location})` : ""}
                        <span className="sub">{p.component_id}</span>
                      </td>
                      <td className="num">{p.useful_life_years} yrs</td>
                      <td className="num">{usd(p.replacement_cost)}</td>
                      <td>{p.planned_years.length ? p.planned_years.join(", ") : <span className="quiet">not in these years</span>}</td>
                      <td>{found.length ? found.map(([y, v]) => `${y}: ${usdShort(v)}`).join(", ") : <span className="quiet">none</span>}</td>
                      <td className="num">{p.repair_spend ? usd(p.repair_spend) : "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}
