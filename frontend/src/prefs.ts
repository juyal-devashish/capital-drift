// Per-browser preferences: colour theme and the collapsed sidebar. They live in
// localStorage (wrapped in try/catch: storage can be unavailable) and broadcast a window event so
// every component showing them stays in sync without a global store.
import { useCallback, useEffect, useState } from "react";

const EVENT = "capital-drift:prefs";

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the value lasts for this page view only */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: key }));
}

/** A localStorage-backed value shared live between components. */
function usePref<T>(key: string, fallback: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => read(key, fallback));
  useEffect(() => {
    const onChange = (e: Event) => {
      if ((e as CustomEvent).detail === key) setValue(read(key, fallback));
    };
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = useCallback((v: T) => write(key, v), [key]);
  return [value, set];
}

// ------------------------------------------------------------------------------------- theme
export type Theme = "light" | "dark" | "system";

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

/** Apply the stored theme before React renders, so the page never flashes the wrong colours. */
export function initTheme() {
  applyTheme(read<Theme>("capital-drift.theme", "system"));
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = usePref<Theme>("capital-drift.theme", "system");
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  return [theme, setTheme];
}

// --------------------------------------------------------------------------------- sidebar
export function useSidebarCollapsed() {
  return usePref<boolean>("capital-drift.sidebarCollapsed", false);
}

// ------------------------------------------------------------------------------ page title
/** Set the browser tab title for the current page. */
export function usePageTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · Capital Drift` : "Capital Drift Monitor";
  }, [title]);
}
