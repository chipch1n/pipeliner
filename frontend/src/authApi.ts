const API_BASE_URL = "/api";

export type UserResponse = {
  username: string;
};

export type UserInfoResponse = {
  user_id: number;
  username: string;
};

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed (${response.status})`;
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    try {
      const payload: unknown = await response.json();
      if (payload && typeof payload === "object" && "detail" in payload) {
        const detail = (payload as { detail: unknown }).detail;
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) {
          const messages = detail
            .map((item) =>
              item && typeof item === "object" && "msg" in item
                ? String((item as { msg: unknown }).msg)
                : null
            )
            .filter(Boolean);
          if (messages.length > 0) return messages.join("; ");
        }
      }
    } catch {
      return fallback;
    }
  }

  const text = await response.text();
  return text || fallback;
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers
    }
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

export function registerUser(username: string, password: string): Promise<UserResponse> {
  return requestJson<UserResponse>("/register", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export function loginUser(username: string, password: string): Promise<UserResponse> {
  return requestJson<UserResponse>("/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export function logoutUser(): Promise<{ message: string }> {
  return requestJson<{ message: string }>("/logout", { method: "POST" });
}

export function fetchCurrentUser(): Promise<UserInfoResponse> {
  return requestJson<UserInfoResponse>("/user-info", { method: "GET" });
}
