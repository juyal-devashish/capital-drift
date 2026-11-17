// Typed API client. Every request carries the bearer token of the signed-in user; errors are
// turned into ApiError with the server's "detail" message so screens can show it verbatim.
import type {
  AssociationTimeline,
  Board,
  CapitalResults,
  ComponentInfo,
  ForecastBoard,
  Me,
  QueueChanges,
  ReviewItemDetail,
  ReviewItemPage,
} from "./types";

const TOKEN_KEY = "capital-drift.token";

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

/** Fired when the server rejects the token, so the auth context can send the user to sign-in. */
export const UNAUTHORIZED_EVENT = "capital-drift:unauthorized";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI validation errors arrive as a list of {loc, msg}; turn them into one readable line. */
function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = d.loc?.filter((p) => p !== "body" && p !== "query").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  return JSON.stringify(detail);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the API is running and try again.");
  }
  if (!res.ok) {
    let detail = res.statusText || `Request failed (${res.status})`;
    try {
      detail = detailText((await res.json()).detail);
    } catch {
      /* non-JSON error body: keep statusText */
    }
    if (res.status === 401) {
      tokenStore.clear();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** Build a query string, skipping empty values. */
export function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface QueueFilters {
  status?: string;
  kind?: string;
  association_id?: string;
  warning_kind?: string;
  limit?: number;
  offset?: number;
}

/** Every item status, for "show all" (an empty status would fall back to the server's default, open). */
export const ALL_ITEM_STATUSES = "open,confirmed,dismissed,resolved,resolved_by_rerun";

export const api = {
  me: () => request<Me>("/me"),
  capital: {
    board: () => request<Board>("/capital/board"),
    association: (id: string) => request<AssociationTimeline>(`/capital/associations/${encodeURIComponent(id)}`),
    queue: (f: QueueFilters) => request<ReviewItemPage>(`/capital/queue${qs(f as Record<string, string | number | undefined>)}`),
    item: (id: string) => request<ReviewItemDetail>(`/capital/queue/${encodeURIComponent(id)}`),
    decide: (id: string, action: "confirm" | "dismiss" | "reopen" | "comment", comment?: string) =>
      request<ReviewItemDetail>(`/capital/queue/${encodeURIComponent(id)}/decisions`, {
        method: "POST",
        body: JSON.stringify({ action, comment }),
      }),
    assign: (invoiceId: string, componentId: string | null, comment?: string) =>
      request<{ item: ReviewItemDetail; changes: QueueChanges }>(`/capital/invoices/${encodeURIComponent(invoiceId)}/assignment`, {
        method: "POST",
        body: JSON.stringify({ component_id: componentId, comment }),
      }),
    components: (associationId: string) => request<ComponentInfo[]>(`/capital/components${qs({ association_id: associationId })}`),
    sync: () => request<QueueChanges>("/capital/queue/sync", { method: "POST" }),
    results: () => request<CapitalResults>("/capital/results"),
    forecast: () => request<ForecastBoard>("/capital/forecast"),
  },
};
