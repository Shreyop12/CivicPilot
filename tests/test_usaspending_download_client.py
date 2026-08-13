import httpx
import pytest
import respx

from civicpilot.clients.usaspending_client import USASPENDING_BASE_URL
from civicpilot.clients.usaspending_download_client import USASpendingDownloadClient


@pytest.mark.asyncio
@respx.mock
async def test_submit_bulk_download_returns_file_name():
    respx.post(f"{USASPENDING_BASE_URL}/bulk_download/awards/").mock(
        return_value=httpx.Response(200, json={"file_name": "job-1", "status_url": "https://example/status"})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        result = await client.submit_bulk_download(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
    assert result["file_name"] == "job-1"


@pytest.mark.asyncio
@respx.mock
async def test_poll_status_returns_running():
    respx.get(f"{USASPENDING_BASE_URL}/download/status/").mock(
        return_value=httpx.Response(200, json={"status": "running"})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        result = await client.poll_status("job-1")
    assert result["status"] == "running"


@pytest.mark.asyncio
@respx.mock
async def test_poll_status_returns_finished_with_file_url():
    respx.get(f"{USASPENDING_BASE_URL}/download/status/").mock(
        return_value=httpx.Response(200, json={"status": "finished", "file_url": "https://example/job-1.csv"})
    )
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        result = await client.poll_status("job-1")
    assert result["file_url"] == "https://example/job-1.csv"


@pytest.mark.asyncio
@respx.mock
async def test_submit_bulk_download_raises_on_http_error():
    respx.post(f"{USASPENDING_BASE_URL}/bulk_download/awards/").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        client = USASpendingDownloadClient(http)
        with pytest.raises(httpx.HTTPStatusError):
            await client.submit_bulk_download(toptier_code="068", start_date="2026-01-01", end_date="2026-03-31")
