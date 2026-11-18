// App shell: a dark sidebar (board, review queue, results, help), a top bar with the user menu and
// theme, and the page area wrapped in an error boundary. On narrow screens the sidebar becomes a
// drawer opened by the hamburger; on wide screens it can collapse to icons.
import { Component, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { snapshotMeta, STATIC } from "../api";
import { ROLE_NAMES, useAuth } from "../auth";
import { useAsync } from "../hooks";
import { useSidebarCollapsed, useTheme, type Theme } from "../prefs";
import { Icon, type IconName } from "./Icons";
import { Tour } from "./Tour";

function NavItem({ to, icon, label, end, active }: { to: string; icon: IconName; label: string; end?: boolean; active?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => ((active ?? isActive) ? "nav-item active" : "nav-item")}
      title={label}
    >
      <Icon name={icon} />
      <span className="nav-label">{label}</span>
    </NavLink>
  );
}

const THEMES: { key: Theme; label: string; icon: IconName }[] = [
  { key: "light", label: "Light", icon: "sun" },
  { key: "dark", label: "Dark", icon: "moon" },
  { key: "system", label: "System", icon: "monitor" },
];

/** Small dropdown menu that closes on outside click or Escape. */
function UserMenu() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  if (!user) return null;
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="user-button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="avatar" aria-hidden="true">
          {user.username[0].toUpperCase()}
        </span>
        <span className="user-button-text">
          <strong>{user.username[0].toUpperCase() + user.username.slice(1)}</strong>
          <small>{ROLE_NAMES[user.role]}</small>
        </span>
        <Icon name="chevronDown" size={16} />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            Signed in as <strong>{user.username}</strong>
            <span className={`role-badge role-${user.role}`}>{ROLE_NAMES[user.role]}</span>
          </div>
          <div className="menu-section">
            <span className="menu-label">Theme</span>
            <div className="segmented" role="group" aria-label="Theme">
              {THEMES.map((t) => (
                <button key={t.key} aria-pressed={theme === t.key} className={theme === t.key ? "is-active" : ""} onClick={() => setTheme(t.key)}>
                  <Icon name={t.icon} size={14} /> {t.label}
                </button>
              ))}
            </div>
          </div>
          <button role="menuitem" className="menu-item" onClick={() => (setOpen(false), navigate("/help"))}>
            <Icon name="help" size={16} /> Help & guide
          </button>
          <button
            role="menuitem"
            className="menu-item danger"
            onClick={() => {
              navigate("/login", { replace: true });
              signOut();
            }}
          >
            <Icon name="logout" size={16} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/** The static snapshot's notice: what this is, when it was taken, and where to run the real thing. */
function SnapshotBanner() {
  const meta = useAsync(() => snapshotMeta(), []);
  return (
    <div className="snapshot-banner" role="note">
      <strong>Demo with made-up data.</strong> Read-only{meta.data ? `, as of ${meta.data.exported_on}` : ""}: buttons that change things are
      turned off here.
    </div>
  );
}

/** Keeps one broken page from blanking the whole app; resets when the user navigates. */
class PageBoundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="empty-state">
        <span className="empty-icon">
          <Icon name="alert" size={26} />
        </span>
        <h3>Something went wrong on this page</h3>
        <p>{this.state.error.message}</p>
        <div className="empty-action">
          <button className="primary" onClick={() => window.location.reload()}>
            Reload the page
          </button>
        </div>
      </div>
    );
  }
}

export function Layout() {
  const location = useLocation();
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  useEffect(() => setDrawer(false), [location.pathname, location.search]);

  return (
    <div className={`shell${collapsed ? " is-collapsed" : ""}${drawer ? " drawer-open" : ""}`}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar" aria-label="Main navigation">
        <div className="sidebar-brand">
          <Link to="/" className="brand">
            <span className="brand-mark" aria-hidden="true">
              <Icon name="check" size={16} />
            </span>
            <span className="brand-name">Capital Drift</span>
          </Link>
          <button className="icon-button sidebar-close" aria-label="Close menu" onClick={() => setDrawer(false)}>
            <Icon name="x" />
          </button>
        </div>

        <nav className="sidebar-scroll">
          <div className="nav-group">
            <NavItem to="/" end icon="building" label="Board view" active={location.pathname === "/" || location.pathname.startsWith("/associations")} />
            <NavItem to="/queue" icon="inbox" label="Review queue" />
            <NavItem to="/results" icon="chart" label="Results" />
          </div>
        </nav>

        <div className="sidebar-foot">
          <NavItem to="/help" icon="help" label="Help & guide" />
          <button className="nav-item collapse-toggle" onClick={() => setCollapsed(!collapsed)} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <Icon name="sidebar" />
            <span className="nav-label">Collapse</span>
          </button>
        </div>
      </aside>
      <div className="drawer-backdrop" onClick={() => setDrawer(false)} aria-hidden="true" />

      <div className="main-col">
        <header className="topbar">
          <button className="icon-button hamburger" aria-label="Open menu" aria-expanded={drawer} onClick={() => setDrawer(true)}>
            <Icon name="menu" />
          </button>
          <span className="topbar-title">Capital Drift Monitor</span>
          <div className="topbar-right">
            <Link to="/help" className="icon-button" title="Help & guide" aria-label="Help & guide">
              <Icon name="help" />
            </Link>
            {STATIC ? (
              <a className="button" href="https://github.com/juyal-devashish/capital-drift" target="_blank" rel="noreferrer">
                <Icon name="external" size={16} /> Code on GitHub
              </a>
            ) : (
              <UserMenu />
            )}
          </div>
        </header>
        <main className="page" id="main">
          {STATIC && <SnapshotBanner />}
          <Tour />
          <PageBoundary resetKey={location.pathname}>
            <Outlet />
          </PageBoundary>
        </main>
      </div>
    </div>
  );
}
