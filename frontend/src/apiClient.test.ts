import { afterEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "./apiClient";

afterEach(() => vi.unstubAllGlobals());

describe("requestJson", () => {
  it("keeps the HTTP status on API errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      headers: { get: () => "application/json" },
      text: () => Promise.resolve('{"detail":"Already signed out"}')
    });
    vi.stubGlobal("fetch", fetchMock);

    const request = requestJson("/logout", { method: "POST" });

    await expect(request).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      message: "Already signed out"
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/logout",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });
});
