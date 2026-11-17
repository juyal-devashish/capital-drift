// Entry point: providers, routes and the sign-in guard.
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ADMIN_ROLES, AuthProvider, CAPITAL_READ_ROLES, QA_ROLES, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { EmptyState, Loading } from "./components/Marks";
import { ToastProvider } from "./components/Toast";
import { initTheme } from "./prefs";
import { AuditLog } from "./pages/AuditLog";
import { Companies } from "./pages/Companies";
import { CompanyView } from "./pages/CompanyView";
import { ExceptionView } from "./pages/ExceptionView";
import { Help } from "./pages/Help";
import { Reports } from "./pages/Reports";
import { Runs } from "./pages/Runs";
import { System } from "./pages/System";
import { Users } from "./pages/Users";
import { CapitalAssociation } from "./pages/capital/Association";
import { Board } from "./pages/capital/Board";
import { CapitalItem } from "./pages/capital/Item";
import { CapitalQueue } from "./pages/capital/Queue";
import { CapitalResults } from "./pages/capital/Results";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Queue } from "./pages/Queue";
import { Rules } from "./pages/Rules";
import { RunView } from "./pages/RunView";
import { Sets } from "./pages/Sets";
import { SetView } from "./pages/SetView";
import { Upload } from "./pages/Upload";
// Fonts are bundled with the app (no third-party requests), so the UI works offline / air-gapped.
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/public-sans/700.css";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/600.css";
import "./styles.css";

initTheme(); // before the first render, so the page never flashes the wrong theme

/** Redirect to sign-in when there is no user (then back here); optionally restrict to admins. */
function Guard({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, ready, can } = useAuth();
  const location = useLocation();
  if (!ready) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (admin && !can(...ADMIN_ROLES))
    return (
      <EmptyState icon="alert" title="Admins only" action={<Link className="button" to="/">Back to overview</Link>}>
        Uploading documents and changing review rules need the admin role. Ask an admin, or sign in as one.
      </EmptyState>
    );
  return <>{children}</>;
}

/** Capital planning screens: board members, property managers, auditors and admins. */
function CapitalGuard({ children }: { children: ReactNode }) {
  const { can } = useAuth();
  if (!can(...CAPITAL_READ_ROLES))
    return (
      <EmptyState icon="shield" title="Capital planning isn't part of your role" action={<Link className="button" to="/">Back to the overview</Link>}>
        Board members, property managers, auditors and admins can open these screens.
      </EmptyState>
    );
  return <>{children}</>;
}

/** Tick & Tie's financial QA screens; capital-only roles are sent to the board view instead. */
function QaGuard({ children }: { children: ReactNode }) {
  const { can } = useAuth();
  return can(...QA_ROLES) ? <>{children}</> : <Navigate to="/capital" replace />;
}

/** Old links used "/?set_id=..." for the queue; send them to its new home. Capital-only roles start on the board. */
function Home() {
  const location = useLocation();
  const { can } = useAuth();
  if (!can(...QA_ROLES)) return <Navigate to="/capital" replace />;
  return location.search ? <Navigate to={`/queue${location.search}`} replace /> : <Overview />;
}

function NotFound() {
  return (
    <EmptyState icon="search" title="Page not found" action={<Link className="button" to="/">Go to the overview</Link>}>
      The link may be out of date, or the item may have been removed.
    </EmptyState>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              element={
                <Guard>
                  <Layout />
                </Guard>
              }
            >
              <Route index element={<Home />} />
              <Route path="capital" element={<CapitalGuard><Board /></CapitalGuard>} />
              <Route path="capital/queue" element={<CapitalGuard><CapitalQueue /></CapitalGuard>} />
              <Route path="capital/queue/:id" element={<CapitalGuard><CapitalItem /></CapitalGuard>} />
              <Route path="capital/associations/:id" element={<CapitalGuard><CapitalAssociation /></CapitalGuard>} />
              <Route path="capital/results" element={<CapitalGuard><CapitalResults /></CapitalGuard>} />
              <Route path="queue" element={<QaGuard><Queue /></QaGuard>} />
              <Route path="exceptions/:id" element={<QaGuard><ExceptionView /></QaGuard>} />
              <Route path="sets" element={<QaGuard><Sets /></QaGuard>} />
              <Route path="sets/:id" element={<QaGuard><SetView /></QaGuard>} />
              <Route path="runs" element={<QaGuard><Runs /></QaGuard>} />
              <Route path="runs/:id" element={<QaGuard><RunView /></QaGuard>} />
              <Route path="companies" element={<QaGuard><Companies /></QaGuard>} />
              <Route path="companies/:id" element={<QaGuard><CompanyView /></QaGuard>} />
              <Route path="reports" element={<QaGuard><Reports /></QaGuard>} />
              <Route path="audit" element={<QaGuard><AuditLog /></QaGuard>} />
              <Route path="help" element={<Help />} />
              <Route path="admin/users" element={<Guard admin><Users /></Guard>} />
              <Route path="admin/system" element={<Guard admin><System /></Guard>} />
              <Route path="upload" element={<Guard admin><Upload /></Guard>} />
              <Route path="rules" element={<Guard admin><Rules /></Guard>} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ToastProvider>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
);
