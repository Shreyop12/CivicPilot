from fastapi import APIRouter, Depends

from ..deps import get_components
from ..schemas import AgencySummary
from ...main import AppComponents

router = APIRouter()


@router.get("/agencies", response_model=list[AgencySummary])
async def list_agencies(components: AppComponents = Depends(get_components)) -> list[AgencySummary]:
    return [
        AgencySummary(name=m.name, toptier_code=m.usaspending_toptier_code, fr_slug=m.fr_slug)
        for m in components.crosswalk.list_all()
    ]
