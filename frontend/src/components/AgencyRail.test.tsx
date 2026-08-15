import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgencyRail } from "./AgencyRail";
import type { AgencySummary } from "../api/types";

const agencies: AgencySummary[] = [
  { name: "Environmental Protection Agency", toptier_code: "068", fr_slug: "environmental-protection-agency" },
  { name: "Department of Energy", toptier_code: "089", fr_slug: "energy-department" },
];

describe("AgencyRail", () => {
  it("lists every agency with its toptier code", () => {
    render(<AgencyRail agencies={agencies} selectedToptierCode={null} onSelect={vi.fn()} />);
    expect(screen.getByText("Environmental Protection Agency")).toBeInTheDocument();
    expect(screen.getByText("068")).toBeInTheDocument();
  });

  it("filters the list as the user types", async () => {
    render(<AgencyRail agencies={agencies} selectedToptierCode={null} onSelect={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Search agencies"), "Energy");

    expect(screen.getByText("Department of Energy")).toBeInTheDocument();
    expect(screen.queryByText("Environmental Protection Agency")).not.toBeInTheDocument();
  });

  it("calls onSelect with the clicked agency", async () => {
    const onSelect = vi.fn();
    render(<AgencyRail agencies={agencies} selectedToptierCode={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByText("Department of Energy"));

    expect(onSelect).toHaveBeenCalledWith(agencies[1]);
  });
});
