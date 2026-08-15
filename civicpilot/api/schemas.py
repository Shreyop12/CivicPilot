from pydantic import BaseModel


class AgencySummary(BaseModel):
    name: str
    toptier_code: str
    fr_slug: str | None


class ObligationYear(BaseModel):
    fiscal_year: int
    amount: float
    partial: bool


class RuleSummary(BaseModel):
    document_number: str
    title: str
    type: str
    publication_date: str
    html_url: str


class AgencyDashboard(BaseModel):
    name: str
    toptier_code: str
    fr_slug: str | None
    obligations: list[ObligationYear]
    rules: list[RuleSummary]


class ChatRequest(BaseModel):
    conversation_id: str
    message: str


class ChatResponse(BaseModel):
    answer: str
    dropped_claims: list[str]
    needs_clarification: bool
    clarification_question: str | None
