export interface AgencySummary {
  name: string;
  toptier_code: string;
  fr_slug: string | null;
}

export interface ObligationYear {
  fiscal_year: number;
  amount: number;
  partial: boolean;
}

export interface RuleSummary {
  document_number: string;
  title: string;
  type: string;
  publication_date: string;
  html_url: string;
}

export interface AgencyDashboard {
  name: string;
  toptier_code: string;
  fr_slug: string | null;
  obligations: ObligationYear[];
  rules: RuleSummary[];
}

export interface ChatResponse {
  answer: string;
  dropped_claims: string[];
  needs_clarification: boolean;
  clarification_question: string | null;
}

export type ChatStreamEvent =
  | { type: "status"; tool: string; message: string }
  | (ChatResponse & { type: "answer" })
  | { type: "error"; detail: string };
