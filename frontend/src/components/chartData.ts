import type { ObligationYear } from "../api/types";

export interface ChartPoint {
  fiscalYear: string;
  amount: number;
  partial: boolean;
}

export function buildChartData(obligations: ObligationYear[]): ChartPoint[] {
  return obligations.map((o) => ({
    fiscalYear: `FY${o.fiscal_year}${o.partial ? " (partial)" : ""}`,
    amount: o.amount,
    partial: o.partial,
  }));
}
