from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_components
from ..schemas import AgencyDashboard, AgencySummary, ObligationYear, RuleSummary
from ...main import AppComponents

router = APIRouter()


def _current_fiscal_year(today: date) -> int:
    return today.year + 1 if today.month >= 10 else today.year


async def build_dashboard(
    components: AppComponents, toptier_code: str, today: date | None = None,
) -> AgencyDashboard:
    today = today or date.today()
    mapping = next(
        (m for m in components.crosswalk.list_all() if m.usaspending_toptier_code == toptier_code),
        None,
    )
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"unknown toptier_code: {toptier_code!r}")

    current_fy = _current_fiscal_year(today)
    fiscal_years = [current_fy - 2, current_fy - 1, current_fy]
    obligations = []
    for fiscal_year in fiscal_years:
        result = await components.usaspending_impl(
            action="spending_by_agency", toptier_code=toptier_code, fiscal_year=fiscal_year,
        )
        obligations.append(
            ObligationYear(
                fiscal_year=fiscal_year,
                amount=result["obligations"],
                partial=(fiscal_year == current_fy),
            )
        )

    start_date = (today - timedelta(days=365)).isoformat()
    fr_result = await components.fr_impl(
        action="search", agency_slug=mapping.fr_slug, doc_type="RULE",
        start_date=start_date, end_date=today.isoformat(),
    )
    rules = [
        RuleSummary(
            document_number=doc["document_number"],
            title=doc["title"],
            type=doc["type"],
            publication_date=doc["publication_date"],
            html_url=doc["html_url"],
        )
        for doc in fr_result.get("results", [])
    ]

    return AgencyDashboard(
        name=mapping.name,
        toptier_code=mapping.usaspending_toptier_code,
        fr_slug=mapping.fr_slug,
        obligations=obligations,
        rules=rules,
    )


@router.get("/agencies", response_model=list[AgencySummary])
async def list_agencies(components: AppComponents = Depends(get_components)) -> list[AgencySummary]:
    return [
        AgencySummary(name=m.name, toptier_code=m.usaspending_toptier_code, fr_slug=m.fr_slug)
        for m in components.crosswalk.list_all()
    ]


@router.get("/agencies/{toptier_code}/dashboard", response_model=AgencyDashboard)
async def get_dashboard(
    toptier_code: str, components: AppComponents = Depends(get_components),
) -> AgencyDashboard:
    return await build_dashboard(components, toptier_code)
