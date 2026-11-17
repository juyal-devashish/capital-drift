// Sign-in. The demo backend issues fixed tokens per role; production would redirect to SSO here.
// Each demo user card says what that role can do, so a first-time visitor can pick the right one.
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Icon } from "../components/Icons";
import { ErrorNote } from "../components/Marks";
import { usePageTitle } from "../prefs";

const DEMO_USERS = [
  { token: "board-token", key: "board_member", name: "Bea", role: "Board member", does: "Sees which associations are red and why; changes nothing" },
  { token: "manager-token", key: "property_manager", name: "Max", role: "Property manager", does: "Works the capital review queue and decides" },
  { token: "analyst-token", key: "analyst", name: "Alice", role: "Analyst", does: "Runs reviews and decides exceptions" },
  { token: "controller-token", key: "controller", name: "Carol", role: "Finance controller", does: "Oversees the queue and decides" },
  { token: "auditor-token", key: "auditor", name: "Arun", role: "Auditor", does: "Reads everything, changes nothing" },
  { token: "admin-token", key: "admin", name: "Adam", role: "Admin", does: "Uploads documents and sets rules" },
];

export function Login() {
  const { user, signIn, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  usePageTitle("Sign in");

  if (user) return <Navigate to={from} replace />;

  async function go(t: string) {
    setError(null);
    setBusy(t);
    try {
      await signIn(t);
      navigate(from, { replace: true });
    } catch (e) {
      setError((e as Error).message === "Invalid token" ? "That token is not recognised." : (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="login-page">
      <section className="login-hero">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Icon name="check" size={16} />
          </span>
          Capital Drift Monitor
        </span>
        <h1>Is the money going where the reserve study said it would?</h1>
        <p className="login-tagline">
          Every invoice placed against a part of the association's reserve study, spending watched against the plan, and a warning when a
          part fails early, a replacement is overdue or a project runs over budget.
        </p>
        <ol className="how-it-works">
          <li>
            <span>
              <strong>Place every invoice.</strong> Rules first, then Claude for the ones the rules can't place.
            </span>
          </li>
          <li>
            <span>
              <strong>Watch spend against the plan.</strong> Warnings read as repair-or-replace calls.
            </span>
          </li>
          <li>
            <span>
              <strong>Check and decide.</strong> Property managers work the queue; the board sees what's red and why.
            </span>
          </li>
        </ol>
        <p className="login-tagline" style={{ fontSize: "0.8125rem", marginTop: "1.5rem" }}>
          All data here is synthetic. Built on Tick &amp; Tie by Shreyash Methi, whose financial QA screens are still here for the analyst,
          controller and auditor roles.
        </p>
      </section>

      <div className="login-side">
        <section className="login-card">
          <h2>Sign in</h2>
          {notice && <p className="notice">{notice}</p>}
          <p className="quiet">Choose a demo user. Each role sees the same data with different permissions.</p>
          <ul className="demo-users">
            {DEMO_USERS.map((u) => (
              <li key={u.token}>
                <button onClick={() => go(u.token)} disabled={!!busy}>
                  <span className="avatar" aria-hidden="true">
                    {u.name[0]}
                  </span>
                  <span className="demo-text">
                    <strong>
                      {u.name} <span className={`role-badge role-${u.key}`}>{u.role}</span>
                    </strong>
                    <small>{u.does}</small>
                  </span>
                  {busy === u.token ? <span className="spinner" aria-hidden="true" /> : <Icon name="chevronRight" />}
                </button>
              </li>
            ))}
          </ul>
          <details className="token-form">
            <summary>Sign in with an access token</summary>
            <form
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                go(token.trim());
              }}
            >
              <label htmlFor="token" className="visually-hidden">
                Access token
              </label>
              <div className="inline-field">
                <input id="token" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" placeholder="Paste a token" />
                <button type="submit" disabled={!token.trim() || !!busy}>
                  Sign in
                </button>
              </div>
            </form>
          </details>
          <ErrorNote message={error} />
        </section>
      </div>
    </main>
  );
}
