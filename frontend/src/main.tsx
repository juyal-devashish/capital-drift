// Entry point: providers, routes and the sign-in guard.
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, HashRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { STATIC } from "./api";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { EmptyState, Loading } from "./components/Marks";
import { ToastProvider } from "./components/Toast";
import { initTheme } from "./prefs";
import { CapitalAssociation } from "./pages/Association";
import { Board } from "./pages/Board";
import { Help } from "./pages/Help";
import { CapitalItem } from "./pages/Item";
import { Login } from "./pages/Login";
import { CapitalQueue } from "./pages/Queue";
import { CapitalResults } from "./pages/Results";
// Fonts are bundled with the app (no third-party requests), so the UI works offline.
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/public-sans/700.css";
import "./styles.css";

initTheme(); // before the first render, so the page never flashes the wrong theme

// Static hosting (GitHub Pages) can't rewrite deep links to index.html, so the snapshot uses #/ URLs.
const Router = STATIC ? HashRouter : BrowserRouter;

/** Redirect to sign-in when there is no user, then back here. */
function Guard({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

function NotFound() {
  return (
    <EmptyState icon="search" title="Page not found" action={<Link className="button" to="/">Go to the board view</Link>}>
      The link may be out of date, or the item may have been removed.
    </EmptyState>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <Router>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={STATIC ? <Navigate to="/" replace /> : <Login />} />
            <Route
              element={
                <Guard>
                  <Layout />
                </Guard>
              }
            >
              <Route index element={<Board />} />
              <Route path="queue" element={<CapitalQueue />} />
              <Route path="queue/:id" element={<CapitalItem />} />
              <Route path="associations/:id" element={<CapitalAssociation />} />
              <Route path="results" element={<CapitalResults />} />
              <Route path="help" element={<Help />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ToastProvider>
      </Router>
    </AuthProvider>
  </StrictMode>,
);
