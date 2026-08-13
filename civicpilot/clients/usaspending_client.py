import httpx

from ..cache import QueryCache

USASPENDING_BASE_URL = "https://api.usaspending.gov/api/v2"


class USASpendingClient:
    def __init__(self, http_client: httpx.AsyncClient, cache: QueryCache):
        self._http = http_client
        self._cache = cache

    async def search_awards(
        self,
        *,
        toptier_code: str,
        start_date: str,
        end_date: str,
        award_type_codes: list[str] | None = None,
        limit: int = 10,
    ) -> dict:
        award_type_codes = award_type_codes or ["A", "B", "C", "D"]
        cache_key = QueryCache.make_key(
            "usaspending.search_awards", toptier_code=toptier_code,
            start_date=start_date, end_date=end_date,
            award_type_codes=award_type_codes, limit=limit,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        body = {
            "filters": {
                "agencies": [{"type": "awarding", "tier": "toptier", "toptier_code": toptier_code}],
                "time_period": [{"start_date": start_date, "end_date": end_date}],
                "award_type_codes": award_type_codes,
            },
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
            "page": 1,
            "limit": limit,
        }
        response = await self._http.post(f"{USASPENDING_BASE_URL}/search/spending_by_award/", json=body)
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result

    async def get_award(self, award_id: str) -> dict:
        cache_key = QueryCache.make_key("usaspending.get_award", award_id=award_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        response = await self._http.get(f"{USASPENDING_BASE_URL}/awards/{award_id}/")
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result

    async def spending_by_agency(self, *, toptier_code: str, fiscal_year: int) -> dict:
        cache_key = QueryCache.make_key(
            "usaspending.spending_by_agency", toptier_code=toptier_code, fiscal_year=fiscal_year,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        response = await self._http.get(
            f"{USASPENDING_BASE_URL}/agency/{toptier_code}/awards/",
            params={"fiscal_year": fiscal_year},
        )
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result
