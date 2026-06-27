import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./apiClient";
import App from "./App";
import { fetchCurrentUser, loginUser, logoutUser, registerUser } from "./authApi";
import { deletePipeline, listPipelines, loadPipeline, savePipeline } from "./pipelineApi";

vi.mock("./authApi", () => ({
  fetchCurrentUser: vi.fn(),
  loginUser: vi.fn(),
  logoutUser: vi.fn(),
  registerUser: vi.fn()
}));

vi.mock("./pipelineApi", () => ({
  deletePipeline: vi.fn(),
  listPipelines: vi.fn(),
  loadPipeline: vi.fn(),
  savePipeline: vi.fn()
}));

const mockedFetchCurrentUser = vi.mocked(fetchCurrentUser);
const mockedLoginUser = vi.mocked(loginUser);
const mockedLogoutUser = vi.mocked(logoutUser);
const mockedRegisterUser = vi.mocked(registerUser);
const mockedDeletePipeline = vi.mocked(deletePipeline);
const mockedListPipelines = vi.mocked(listPipelines);
const mockedLoadPipeline = vi.mocked(loadPipeline);
const mockedSavePipeline = vi.mocked(savePipeline);

afterEach(cleanup);

describe("App authentication and presets", () => {
  beforeEach(() => {
    mockedFetchCurrentUser.mockReset();
    mockedFetchCurrentUser.mockRejectedValue(new ApiError(401, "Not authenticated"));
    mockedLoginUser.mockReset();
    mockedLogoutUser.mockReset();
    mockedRegisterUser.mockReset();
    mockedDeletePipeline.mockReset();
    mockedListPipelines.mockReset();
    mockedListPipelines.mockResolvedValue([]);
    mockedLoadPipeline.mockReset();
    mockedSavePipeline.mockReset();
  });

  it("shows validation only after the user enters an invalid value", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
    await user.type(screen.getByLabelText("Username"), "ab");

    expect(screen.getByRole("status")).toHaveTextContent(
      "Username must contain at least 3 characters"
    );
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("treats logout HTTP 400 as an already closed session regardless of error text", async () => {
    mockedFetchCurrentUser.mockResolvedValue({ user_id: 7, username: "alice" });
    mockedLogoutUser.mockRejectedValue(new ApiError(400, "Session disappeared"));
    render(<App />);

    const user = userEvent.setup();
    expect(await screen.findByText("alice")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Logout" }));

    expect(await screen.findByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.queryByText("Session disappeared")).not.toBeInTheDocument();
  });

  it("loads a saved preset for the authenticated user", async () => {
    mockedFetchCurrentUser.mockResolvedValue({ user_id: 7, username: "alice" });
    mockedListPipelines.mockResolvedValue([{ id: 11, name: "portrait" }]);
    mockedLoadPipeline.mockResolvedValue({
      id: 11,
      name: "portrait",
      pipeline_data: {
        nodes: [{ id: "blur-1", type: "blur", branch: "main", params: { radius: 4 } }],
        branch_sources: { main: "original" }
      }
    });
    render(<App />);

    const user = userEvent.setup();
    const presets = await screen.findByLabelText("Saved presets");
    await user.selectOptions(presets, "portrait");
    await user.click(screen.getByRole("button", { name: "Load" }));

    await waitFor(() => expect(mockedLoadPipeline).toHaveBeenCalledWith("portrait"));
    expect(await screen.findByText("BLUR")).toBeInTheDocument();
    expect(screen.getByText('Preset "portrait" loaded')).toBeInTheDocument();
  });

  it("saves the current pipeline under a user-provided preset name", async () => {
    mockedFetchCurrentUser.mockResolvedValue({ user_id: 7, username: "alice" });
    mockedSavePipeline.mockResolvedValue({ id: 12 });
    mockedListPipelines
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: 12, name: "empty-start" }]);
    render(<App />);

    const user = userEvent.setup();
    await screen.findByText("alice");
    await user.type(screen.getByLabelText("Preset name"), "empty-start");
    await user.click(screen.getByRole("button", { name: "Save preset" }));

    await waitFor(() => expect(mockedSavePipeline).toHaveBeenCalledWith("empty-start", [], {}));
    expect(await screen.findByText('Preset "empty-start" saved')).toBeInTheDocument();
  });
});
