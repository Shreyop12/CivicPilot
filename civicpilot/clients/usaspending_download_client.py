import httpx

from .usaspending_client import USASPENDING_BASE_URL


class USASpendingDownloadClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client

    async def submit_bulk_download(self, *, toptier_code: str, start_date: str, end_date: str) -> dict:
        body = {
            "filters": {
                "agencies": [{"type": "awarding", "tier": "toptier", "toptier_code": toptier_code}],
                "time_period": [{"start_date": start_date, "end_date": end_date}],
            },
            "file_format": "csv",
        }
        response = await self._http.post(f"{USASPENDING_BASE_URL}/bulk_download/awards/", json=body)
        response.raise_for_status()
        return response.json()

    async def poll_status(self, file_name: str) -> dict:
        response = await self._http.get(
            f"{USASPENDING_BASE_URL}/download/status/", params={"file_name": file_name},
        )
        response.raise_for_status()
        return response.json()
