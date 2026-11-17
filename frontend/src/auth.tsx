// Auth context: holds the signed-in user (resolved from the stored token via /api/me) and
// exposes role checks so screens can hide actions a role may not perform. The server enforces
// the same rules; hiding them here only keeps the UI honest.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokenStore, UNAUTHORIZED_EVENT } from "./api";
import type { Me, Role } from "./types";

interface AuthState {
  user: Me | null;
  ready: boolean;
  /** Why the user was signed out, shown once on the sign-in screen. */
  notice: string | null;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
  can: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!tokenStore.get()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setReady(true));
  }, []);

  // A 401 anywhere means the token is no longer valid: drop the user so the guard redirects.
  useEffect(() => {
    const onUnauthorized = () => {
      setUser((current) => {
        if (current) setNotice("Your session has ended. Sign in again to continue.");
        return null;
      });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const signIn = useCallback(async (token: string) => {
    tokenStore.set(token);
    try {
      setUser(await api.me());
      setNotice(null);
    } catch (e) {
      tokenStore.clear();
      throw e;
    }
  }, []);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  const can = useCallback((...roles: Role[]) => !!user && roles.includes(user.role), [user]);

  return (
    <AuthContext.Provider value={{ user, ready, notice, signIn, signOut, can }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// Role groups, mirroring backend/app/core/security.py.
export const REVIEW_ROLES: Role[] = ["analyst", "controller", "admin"];
export const RUN_ROLES: Role[] = ["analyst", "admin"];
export const ADMIN_ROLES: Role[] = ["admin"];
/** Tick & Tie's financial QA screens (documents, exceptions, reviews). */
export const QA_ROLES: Role[] = ["analyst", "controller", "auditor", "admin"];
/** Capital planning (Capital Drift): board members read, property managers decide. */
export const CAPITAL_READ_ROLES: Role[] = ["board_member", "property_manager", "auditor", "admin"];
export const CAPITAL_DECIDE_ROLES: Role[] = ["property_manager", "admin"];

export const ROLE_NAMES: Record<Role, string> = {
  analyst: "Analyst",
  controller: "Finance controller",
  auditor: "Auditor",
  admin: "Admin",
  board_member: "Board member",
  property_manager: "Property manager",
};
