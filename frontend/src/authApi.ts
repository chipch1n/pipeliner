import { requestJson } from "./apiClient";

export type UserResponse = {
  username: string;
};

export type UserInfoResponse = {
  user_id: number;
  username: string;
};

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
