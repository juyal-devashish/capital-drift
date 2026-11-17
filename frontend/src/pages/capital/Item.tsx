// One review item. A warning shows its message, the invoices behind it and, when past due, the
// candidate invoices that may be the missing replacement. Property managers place invoices against
// a part (the warnings rerun at once and the page says what changed) and confirm or dismiss warnings.
// Everyone with access sees the full history.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { CAPITAL_DECIDE_ROLES, ROLE_NAMES, useAuth } from "../../auth";
import { ErrorNote, Loading } from "../../components/Marks";
import { useToast } from "../../components/Toast";
import { WARNING_NAMES, dateTime, usd } from "../../format";
import { useAsync } from "../../hooks";
import { usePageTitle } from "../../prefs";
import type { ComponentInfo, QueueChanges, RelatedInvoice, Role } from "../../types";
import { SyntheticNote } from "./Board";
import { ItemStatus, ItemTag } from "./Queue";

function matchName(m: { label: string; component_id: string | null } | null, byId: Map<string, ComponentInfo>): string {
  if (!m || m.label === "unsure") return "unplaced";
  return partName(byId.get(m.component_id ?? ""), m.component_id);
}

function partName(c: ComponentInfo | undefined, id: string | null): string {
  if (!id) return "Routine upkeep";
  if (!c) return id;
  return c.location ? `${c.name} (${c.location})` : c.name;
}

function Assign({
  invoice,
  parts,
  suggested,
  onDone,
}: {
  invoice: RelatedInvoice;
  parts: ComponentInfo[];
  suggested: string | null;
  onDone: (changes: QueueChanges) => void;
}) {
  const toast = useToast();
  const [choice, setChoice] = useState<string>(suggested ?? invoice.component_id ?? "");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      const res = await api.capital.assign(invoice.id, choice === "routine" ? null : choice);
      onDone(res.changes);
    } catch (e) {
      toast((e as Error).message, { tone: "error" });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="assign-row">
      <label className="visually-hidden" htmlFor={`assign-${invoice.id}`}>
        Part for invoice {invoice.id}
      </label>
      <select id={`assign-${invoice.id}`} value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="" disabled>
          Choose the part…
        </option>
        <option value="routine">Routine upkeep (not a reserve part)</option>
        {parts.map((p) => (
          <option key={p.id} value={p.id}>
            {partName(p, p.id)}
          </option>
        ))}
      </select>
      <button className="primary" disabled={!choice || busy} onClick={save}>
        {busy ? "Saving…" : "Place it"}
      </button>
    </div>
  );
}

/** "W:overdue:A10-BOIL-A:2020" -> "Past due: A10-BOIL-A (2020 plan)"; "I:INV-1" -> "Invoice INV-1". */
function keyText(id: string): string {
  const [kind, a, b, c] = id.split(":");
  if (kind === "I") return `Invoice ${a}`;
  return `${WARNING_NAMES[a] ?? a}: ${b} (${c} ${a === "over_budget" ? "project" : "plan"})`;
}

function Changes({ changes }: { changes: QueueChanges }) {
  const link = (id: string) => <Link to={`/capital/queue/${encodeURIComponent(id)}`}>{keyText(id)}</Link>;
  const none = !changes.opened.length && !changes.reopened.length && !changes.resolved_by_rerun.length;
  return (
    <section className="panel" aria-live="polite">
      <h2>What the rerun changed</h2>
      {none ? (
        <p className="quiet">No warning appeared or cleared.</p>
      ) : (
        <div className="changes">
          {changes.resolved_by_rerun.map((id) => (
            <span key={id} className="cleared">
              No longer raised: {link(id)}
            </span>
          ))}
          {[...changes.opened, ...changes.reopened].map((id) => (
            <span key={id} className="raised">
              Raised: {link(id)}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

export function CapitalItem() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const toast = useToast();
  const item = useAsync(() => api.capital.item(id), [id]);
  const parts = useAsync(
    () => (item.data ? api.capital.components(item.data.association_id) : Promise.resolve([] as ComponentInfo[])),
    [item.data?.association_id],
  );
  const [changes, setChanges] = useState<QueueChanges | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  usePageTitle(item.data?.title ?? "Review item");
  useEffect(() => setChanges(null), [id]);

  if (item.error) return <ErrorNote message={item.error} onRetry={item.reload} />;
  if (!item.data) return <Loading />;
  const it = item.data;
  const decide = can(...CAPITAL_DECIDE_ROLES);
  const byId = new Map((parts.data ?? []).map((p) => [p.id, p]));
  const candidates = it.invoices.filter((i) => i.role === "candidate");
  const evidence = it.invoices.filter((i) => i.role === "evidence");

  async function act(action: "confirm" | "dismiss" | "reopen" | "comment") {
    setBusy(true);
    try {
      item.setData(await api.capital.decide(it.id, action, comment.trim() || undefined));
      setComment("");
    } catch (e) {
      toast((e as Error).message, { tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  function placed(ch: QueueChanges) {
    setChanges(ch);
    item.reload();
  }

  const invoiceTable = (rows: RelatedInvoice[], title: string, hint: string, suggest: string | null) =>
    rows.length > 0 && (
      <section className="stack">
        <div>
          <h2 style={{ marginBottom: "0.25rem" }}>{title}</h2>
          <p className="quiet" style={{ margin: 0 }}>
            {hint}
          </p>
        </div>
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>Invoice</th>
                <th className="num">Amount</th>
                <th>Placed against</th>
                {decide && <th>Place it against</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((inv) => (
                <tr key={inv.id} className={inv.role === "candidate" ? "candidate-row" : undefined}>
                  <td>
                    <strong>{inv.memo}</strong>
                    <span className="sub">
                      {inv.vendor_name} · {inv.invoice_date} · {inv.id} · booked to {inv.fund_booked}
                    </span>
                  </td>
                  <td className="num nowrap">{usd(inv.amount)}</td>
                  <td>
                    {inv.label === "unsure" ? <span className="quiet">Nobody could place it</span> : partName(byId.get(inv.component_id ?? ""), inv.component_id)}
                    <span className="sub">
                      {inv.label === "unsure" ? "" : `${inv.label}, by ${inv.method === "llm" ? "Claude" : inv.method}`}
                    </span>
                  </td>
                  {decide && (
                    <td>
                      <Assign invoice={inv} parts={parts.data ?? []} suggested={suggest} onDone={placed} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    );

  return (
    <>
      <header className="page-head with-actions">
        <div>
          <p className="eyebrow">
            <Link to="/capital/queue">Review queue</Link> · <Link to={`/capital/associations/${encodeURIComponent(it.association_id)}`}>{it.association_id}</Link>
          </p>
          <h1>{it.title}</h1>
          <div className="assign-row">
            <ItemTag item={it} /> <ItemStatus status={it.status} /> <span className="quiet">since {it.opened_on}</span>
          </div>
        </div>
        <SyntheticNote />
      </header>

      <div className="stack">
        <section className="panel">
          <p style={{ margin: 0 }}>{it.payload.message ?? it.detail}</p>
        </section>

        {changes && <Changes changes={changes} />}

        {it.status === "resolved_by_rerun" && (
          <p className="rule-note">A rerun no longer raises this warning, so there is nothing to decide. If it comes back, it reopens here.</p>
        )}

        {it.status === "open" &&
          invoiceTable(
          candidates,
          "Could one of these be the replacement?",
          "Invoices from this association, big enough to be part of a replacement, that nobody could place or that went to the same kind of part in another building. Placing them correctly reruns the warnings.",
          null, // no default: a candidate may well belong to the look-alike part
        )}
        {invoiceTable(
          evidence,
          it.kind === "invoice" ? "The invoice" : "The invoices behind this warning",
          it.kind === "invoice" ? "Pick the part of the reserve study it paid for, or mark it routine upkeep." : "As currently placed.",
          null,
        )}

        {decide && it.kind === "warning" && it.status !== "resolved_by_rerun" && (
          <section className="panel">
            <h2>Decision</h2>
            <label className="field-label" htmlFor="comment">
              Comment (needed to dismiss)
            </label>
            <textarea id="comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="What you found, for the board and the log" />
            <div className="assign-row" style={{ marginTop: "0.75rem" }}>
              {it.status === "open" ? (
                <>
                  <button className="primary" disabled={busy} onClick={() => act("confirm")}>
                    Confirm: it's real
                  </button>
                  <button disabled={busy || !comment.trim()} onClick={() => act("dismiss")}>
                    Dismiss
                  </button>
                </>
              ) : (
                <button disabled={busy} onClick={() => act("reopen")}>
                  Reopen
                </button>
              )}
              <button className="quiet-button" disabled={busy || !comment.trim()} onClick={() => act("comment")}>
                Add comment only
              </button>
            </div>
          </section>
        )}

        <section className="stack">
          <h2 style={{ margin: 0 }}>History</h2>
          <div className="table-wrap">
            <table className="ledger compact">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>What</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {it.actions.map((a) => (
                  <tr key={a.id}>
                    <td className="nowrap">{dateTime(a.created_at)}</td>
                    <td>
                      {a.username}
                      <span className="sub">{a.username === "system" ? "automatic rerun" : (ROLE_NAMES[a.role as Role] ?? a.role)}</span>
                    </td>
                    <td>
                      {a.action}
                      {a.match_after && (
                        <span className="sub">
                          {matchName(a.match_before, byId)} → {matchName(a.match_after, byId)}
                        </span>
                      )}
                      {a.comment && <span className="sub">“{a.comment}”</span>}
                    </td>
                    <td className="nowrap">
                      {a.status_before ? `${a.status_before} → ` : ""}
                      {a.status_after}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}
