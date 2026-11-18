// Capital review queue: warnings first (the money at stake), then invoices nobody could place.
// Board members read it; property managers and admins open an item to decide.
import { Link, useSearchParams } from "react-router-dom";
import { ALL_ITEM_STATUSES, api } from "../api";
import { ADMIN_ROLES, CAPITAL_DECIDE_ROLES, useAuth } from "../auth";
import { EmptyState, ErrorNote, SkeletonRows } from "../components/Marks";
import { useToast } from "../components/Toast";
import { ITEM_STATUS_NAMES, WARNING_NAMES, plural, usd } from "../format";
import { useAsync } from "../hooks";
import { usePageTitle } from "../prefs";
import type { ReviewItem } from "../types";
import { SyntheticNote } from "./Board";

const VIEWS = [
  { key: "warning", label: "Warnings" },
  { key: "invoice", label: "Unplaced invoices" },
] as const;

export function ItemTag({ item }: { item: Pick<ReviewItem, "kind" | "warning_kind"> }) {
  return item.kind === "warning" && item.warning_kind ? (
    <span className={`kind-tag kind-${item.warning_kind}`}>{WARNING_NAMES[item.warning_kind]}</span>
  ) : (
    <span className="kind-tag">Unplaced invoice</span>
  );
}

export function ItemStatus({ status }: { status: string }) {
  return <span className={`status status-${status}`}>{ITEM_STATUS_NAMES[status] ?? status}</span>;
}

export function CapitalQueue() {
  usePageTitle("Review queue");
  const { can } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "warning";
  const showAll = params.get("all") === "1";
  const association = params.get("association_id") ?? undefined;
  const page = useAsync(
    () => api.capital.queue({ kind, association_id: association, status: showAll ? ALL_ITEM_STATUSES : "open", limit: 200 }),
    [kind, showAll, association],
  );

  function set(next: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    Object.entries(next).forEach(([k, v]) => (v === null ? p.delete(k) : p.set(k, v)));
    setParams(p, { replace: true });
  }

  async function rebuild() {
    try {
      const ch = await api.capital.sync();
      toast(
        `Queue rebuilt: ${ch.opened.length} new, ${ch.reopened.length} raised again, ${ch.resolved_by_rerun.length} no longer raised.`,
      );
      page.reload();
    } catch (e) {
      toast((e as Error).message, { tone: "error" });
    }
  }

  return (
    <>
      <header className="page-head with-actions">
        <div>
          <h1>Review queue</h1>
          <p className="lede">
            {can(...CAPITAL_DECIDE_ROLES)
              ? "Warnings for a person to check, most important first. Start with the past-due ones."
              : "Warnings a property manager checks before anything is decided. Click one to see the evidence."}
          </p>
        </div>
        <div className="assign-row">
          <SyntheticNote />
          {can(...ADMIN_ROLES) && <button onClick={rebuild}>Rebuild queue</button>}
        </div>
      </header>

      <div className="assign-row" style={{ marginBottom: "1rem" }}>
        <div className="chip-group" role="group" aria-label="What to show">
          {VIEWS.map((v) => (
            <button key={v.key} className={`chip${kind === v.key ? " is-active" : ""}`} aria-pressed={kind === v.key} onClick={() => set({ kind: v.key })}>
              {v.label}
            </button>
          ))}
        </div>
        <label className="quiet">
          <input type="checkbox" checked={showAll} onChange={(e) => set({ all: e.target.checked ? "1" : null })} /> Include decided items
        </label>
        {association && (
          <button className="quiet-button" onClick={() => set({ association_id: null })}>
            Association {association} ✕
          </button>
        )}
      </div>

      <ErrorNote message={page.error} onRetry={page.reload} />
      {!page.data ? (
        <SkeletonRows />
      ) : page.data.items.length === 0 ? (
        <EmptyState icon="check" title="Nothing waiting here">
          {kind === "warning" ? "Every warning has been checked." : "Every invoice has been placed against the plan."}
        </EmptyState>
      ) : (
        <>
          <p className="quiet">{plural(page.data.total, kind === "warning" ? "warning" : "invoice")}</p>
          <div className="table-wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th>What</th>
                  <th>Association</th>
                  <th className="num">At stake</th>
                  <th>Since</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {page.data.items.map((i) => (
                  <tr key={i.id}>
                    <td className="title-cell">
                      <Link className="row-link" to={`/queue/${encodeURIComponent(i.id)}`}>
                        {i.title}
                        <small>
                          <ItemTag item={i} />
                        </small>
                      </Link>
                    </td>
                    <td>
                      <Link to={`/associations/${encodeURIComponent(i.association_id)}`}>{i.association_id}</Link>
                    </td>
                    <td className="num">{usd(i.amount_at_stake)}</td>
                    <td className="nowrap">{i.opened_on}</td>
                    <td>
                      <ItemStatus status={i.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
