import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { fetchAgencies, fetchDashboard } from "./api/client";

vi.mock("./api/client", () => ({
  fetchAgencies: vi.fn(),
  fetchDashboard: vi.fn(),
  streamChat: vi.fn(),
}));

describe("App", () => {
  it("loads agencies, shows a placeholder before selection, and loads the dashboard on select", async () => {
    vi.mocked(fetchAgencies).mockResolvedValue([
      { name: "Environmental Protection Agency", toptier_code: "068", fr_slug: "environmental-protection-agency" },
    ]);
    vi.mocked(fetchDashboard).mockResolvedValue({
      name: "Environmental Protection Agency",
      toptier_code: "068",
      fr_slug: "environmental-protection-agency",
      obligations: [],
      rules: [],
    });

    render(<App />);

    expect(screen.getByText(/select an agency/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument());

    await userEvent.click(screen.getByText("Environmental Protection Agency"));

    await waitFor(() => expect(fetchDashboard).toHaveBeenCalledWith("068"));
  });
});
