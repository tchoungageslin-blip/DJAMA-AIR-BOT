/**
 * API helper with automatic auth token injection.
 */

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export async function apiFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });

  // Auto-redirect on 401
  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("token");
    localStorage.removeItem("agent");
    window.location.href = "/login";
  }

  return res;
}

export async function apiGet(url: string) {
  return apiFetch(url);
}

export async function apiPost(url: string, body?: unknown) {
  return apiFetch(url, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}
