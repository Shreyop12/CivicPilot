import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgencyRecord } from "./AgencyRecord";
import { fetchDashboard } from "../api/client";

vi.mock("../api/client", () => ({
  fetchDashboard: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

const mockDashboard = {
  name: "Environmental Protection Agency",
  toptier_code: "068",
  fr_slug: "environmental-protection-agency",
  obligations: [
    { fiscal_year: 2024, amount: 27274197006.76, partial: false },
    { fiscal_year: 2025, amount: 29100000000, partial: false },
    { fiscal_year: 2026, amount: 10797760149.61, partial: true },
  ],
  rules: [
    {
      document_number: "2026-16627",
      title: "National Emission Standards",
      type: "RULE",
      publication_date: "2026-08-01",
      html_url: "https://www.federalregister.gov/documents/2026-16627",
    },
  ],
};

describe("AgencyRecord", () => {
  it("renders the agency name and rules after loading", async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(mockDashboard);
    render(<AgencyRecord toptierCode="068" />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument());

    expect(screen.getByText("National Emission Standards")).toBeInTheDocument();
    expect(screen.getByText("[doc:2026-16627]")).toBeInTheDocument();
  });

  it("shows an error state with a working retry button", async () => {
    vi.mocked(fetchDashboard).mockRejectedValueOnce(new Error("network error"));
    render(<AgencyRecord toptierCode="068" />);

    await waitFor(() => expect(screen.getByText(/couldn't load/i)).toBeInTheDocument());

    vi.mocked(fetchDashboard).mockResolvedValueOnce(mockDashboard);
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument());
  });

  it("shows empty-state text when there is no data", async () => {
    vi.mocked(fetchDashboard).mockResolvedValue({ ...mockDashboard, obligations: [], rules: [] });
    render(<AgencyRecord toptierCode="068" />);

    await waitFor(() => expect(screen.getByText(/no obligation data available/i)).toBeInTheDocument());
    expect(screen.getByText(/no final rules issued/i)).toBeInTheDocument();
  });
});
