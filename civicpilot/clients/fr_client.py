import httpx

from ..cache import QueryCache

FR_BASE_URL = "https://www.federalregister.gov/api/v1"


class FederalRegisterClient:
    def __init__(self, http_client: httpx.AsyncClient, cache: QueryCache):
        self._http = http_client
        self._cache = cache

    async def search_documents(
        self,
        *,
        agency_slug: str | None = None,
        doc_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        per_page: int = 20,
    ) -> dict:
        cache_key = QueryCache.make_key(
            "fr.search", agency_slug=agency_slug, doc_type=doc_type,
            start_date=start_date, end_date=end_date, per_page=per_page,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params: dict[str, object] = {"per_page": per_page}
        if agency_slug:
            params["conditions[agencies][]"] = agency_slug
        if doc_type:
            params["conditions[type][]"] = doc_type
        if start_date:
            params["conditions[publication_date][gte]"] = start_date
        if end_date:
            params["conditions[publication_date][lte]"] = end_date

        response = await self._http.get(f"{FR_BASE_URL}/documents.json", params=params)
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result

    async def get_document(self, document_number: str) -> dict:
        cache_key = QueryCache.make_key("fr.get", document_number=document_number)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        response = await self._http.get(f"{FR_BASE_URL}/documents/{document_number}.json")
        response.raise_for_status()
        result = response.json()
        self._cache.set(cache_key, result)
        return result
