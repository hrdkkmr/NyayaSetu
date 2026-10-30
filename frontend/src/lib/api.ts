/**
 * API client. Requests go to same-origin `/api/v1/*` (proxied to the backend by Next.js),
 * so authentication cookies are first-party. Unsafe requests echo the CSRF cookie.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

const BASE = "/api/v1";

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)ns_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  refreshing ??= fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
    body: "{}",
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      setTimeout(() => (refreshing = null), 0);
    });
  return refreshing;
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; raw?: boolean };

export async function api<T = unknown>(path: string, options: Options = {}, retried = false): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }
  if (!["GET", "HEAD"].includes(method)) headers.set("X-CSRF-Token", csrfToken());

  const res = await fetch(`${BASE}${path}`, { ...options, method, headers, body, credentials: "include" });
  if (res.status === 401 && !retried && !path.startsWith("/auth/")) {
    if (await tryRefresh()) return api<T>(path, options, true);
  }
  if (!res.ok) {
    let code = "http_error";
    let message = "Something went wrong. Please try again.";
    let details: unknown;
    try {
      const data = await res.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
      details = data?.error?.details;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, code, message, details);
  }
  if (options.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function download(path: string, filename: string): Promise<void> {
  const res = await api<Response>(path, { raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function wsBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_WS_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}
