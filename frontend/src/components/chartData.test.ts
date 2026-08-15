import { describe, expect, it } from "vitest";
import { buildChartData } from "./chartData";

describe("buildChartData", () => {
  it("labels the partial fiscal year distinctly from closed years", () => {
    const result = buildChartData([
      { fiscal_year: 2024, amount: 100, partial: false },
      { fiscal_year: 2025, amount: 200, partial: false },
      { fiscal_year: 2026, amount: 50, partial: true },
    ]);

    expect(result).toEqual([
      { fiscalYear: "FY2024", amount: 100 },
      { fiscalYear: "FY2025", amount: 200 },
      { fiscalYear: "FY2026 (partial)", amount: 50 },
    ]);
  });
});
