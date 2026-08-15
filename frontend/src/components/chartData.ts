import type { ObligationYear } from "../api/types";

export interface ChartPoint {
  fiscalYear: string;
  amount: number;
}

export function buildChartData(obligations: ObligationYear[]): ChartPoint[] {
  return obligations.map((o) => ({
    fiscalYear: `FY${o.fiscal_year}${o.partial ? " (partial)" : ""}`,
    amount: o.amount,
  }));
}
