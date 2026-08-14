import asyncio
import time

from mcp.server.fastmcp import FastMCP

from ..clients.usaspending_client import USASpendingClient
from ..clients.usaspending_download_client import USASpendingDownloadClient

MAX_POLL_WINDOW_SECONDS = 8
POLL_INTERVAL_SECONDS = 2


async def _query_spending_impl(
    client: USASpendingClient,
    download_client: USASpendingDownloadClient,
    *,
    action: str,
    toptier_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    award_id: str | None = None,
    fiscal_year: int | None = None,
    job_id: str | None = None,
) -> dict:
    if action == "search_awards":
        if not (toptier_code and start_date and end_date):
            raise ValueError("start_date and end_date are required for action='search_awards'")
        return await client.search_awards(toptier_code=toptier_code, start_date=start_date, end_date=end_date)
    if action == "get_award":
        if not award_id:
            raise ValueError("award_id is required for action='get_award'")
        return await client.get_award(award_id)
    if action == "spending_by_agency":
        if not (toptier_code and fiscal_year):
            raise ValueError("fiscal_year is required for action='spending_by_agency'")
        return await client.spending_by_agency(toptier_code=toptier_code, fiscal_year=fiscal_year)
    if action == "submit_bulk_download":
        if not (toptier_code and start_date and end_date):
            raise ValueError("toptier_code, start_date and end_date are required for action='submit_bulk_download'")
        return await _submit_spending_query_impl(
            download_client, toptier_code=toptier_code, start_date=start_date, end_date=end_date,
        )
    if action == "get_bulk_download_result":
        if not job_id:
            raise ValueError("job_id is required for action='get_bulk_download_result'")
        return await _get_spending_result_impl(download_client, job_id=job_id)
    raise ValueError(
        f"unsupported action: {action!r}. Supported actions: 'search_awards', 'get_award', "
        "'spending_by_agency', 'submit_bulk_download', 'get_bulk_download_result'."
    )


async def _submit_spending_query_impl(
    download_client: USASpendingDownloadClient,
    *,
    toptier_code: str,
    start_date: str,
    end_date: str,
    poll_window_seconds: int = MAX_POLL_WINDOW_SECONDS,
    poll_interval_seconds: int = POLL_INTERVAL_SECONDS,
    sleep=asyncio.sleep,
    clock=time.monotonic,
) -> dict:
    submission = await download_client.submit_bulk_download(
        toptier_code=toptier_code, start_date=start_date, end_date=end_date,
    )
    file_name = submission["file_name"]
    deadline = clock() + poll_window_seconds
    while clock() < deadline:
        status = await download_client.poll_status(file_name)
        if status["status"] == "finished":
            return {"status": "complete", "file_url": status["file_url"], "job_id": file_name}
        if status["status"] == "failed":
            return {"status": "failed", "job_id": file_name, "message": status.get("message", "download failed")}
        await sleep(poll_interval_seconds)
    return {"status": "pending", "job_id": file_name}


async def _get_spending_result_impl(download_client: USASpendingDownloadClient, *, job_id: str) -> dict:
    status = await download_client.poll_status(job_id)
    if status["status"] == "finished":
        return {"status": "complete", "file_url": status["file_url"], "job_id": job_id}
    if status["status"] == "failed":
        return {"status": "failed", "job_id": job_id, "message": status.get("message", "download failed")}
    return {"status": "pending", "job_id": job_id}


def build_usaspending_server(
    client: USASpendingClient, download_client: USASpendingDownloadClient,
) -> FastMCP:
    server = FastMCP("usaspending")

    async def query_spending(
        action: str,
        toptier_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        award_id: str | None = None,
        fiscal_year: int | None = None,
        job_id: str | None = None,
    ) -> dict:
        """Query USAspending data. action: 'search_awards', 'get_award', 'spending_by_agency',
        'submit_bulk_download' (starts an award-list export, returns inline within ~8s or a job_id),
        or 'get_bulk_download_result' (polls a job_id from a prior submit_bulk_download call)."""
        return await _query_spending_impl(
            client, download_client, action=action, toptier_code=toptier_code, start_date=start_date,
            end_date=end_date, award_id=award_id, fiscal_year=fiscal_year, job_id=job_id,
        )

    server.tool()(query_spending)
    server._query_spending_impl = query_spending
    return server
