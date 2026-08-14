# tests/test_usaspending_server.py
from unittest.mock import AsyncMock

import pytest

from civicpilot.servers.usaspending_server import MAX_POLL_WINDOW_SECONDS, _query_spending_impl


@pytest.mark.asyncio
async def test_query_spending_search_awards_requires_dates():
    client = AsyncMock()
    download_client = AsyncMock()
    with pytest.raises(ValueError, match="start_date and end_date are required"):
        await _query_spending_impl(client, download_client, action="search_awards", toptier_code="068")


@pytest.mark.asyncio
async def test_query_spending_dispatches_search_awards():
    client = AsyncMock()
    client.search_awards.return_value = {"results": []}
    download_client = AsyncMock()
    result = await _query_spending_impl(
        client, download_client, action="search_awards", toptier_code="068",
        start_date="2026-01-01", end_date="2026-03-31",
    )
    assert result == {"results": []}


@pytest.mark.asyncio
async def test_query_spending_dispatches_get_award():
    client = AsyncMock()
    client.get_award.return_value = {"id": "AWD-1"}
    download_client = AsyncMock()
    result = await _query_spending_impl(client, download_client, action="get_award", award_id="AWD-1")
    assert result == {"id": "AWD-1"}


@pytest.mark.asyncio
async def test_query_spending_dispatches_spending_by_agency():
    client = AsyncMock()
    client.spending_by_agency.return_value = {"total_obligations": 4200000}
    download_client = AsyncMock()
    result = await _query_spending_impl(
        client, download_client, action="spending_by_agency", toptier_code="068", fiscal_year=2026,
    )
    assert result == {"total_obligations": 4200000}


@pytest.mark.asyncio
async def test_query_spending_unsupported_action_raises():
    client = AsyncMock()
    download_client = AsyncMock()
    with pytest.raises(ValueError, match="unsupported action"):
        await _query_spending_impl(client, download_client, action="delete_everything", toptier_code="068")


from civicpilot.servers.usaspending_server import _get_spending_result_impl, _submit_spending_query_impl


@pytest.mark.asyncio
async def test_submit_returns_complete_when_job_finishes_within_window():
    download_client = AsyncMock()
    download_client.submit_bulk_download.return_value = {"file_name": "job-1"}
    download_client.poll_status.return_value = {"status": "finished", "file_url": "https://example/job-1.csv"}

    fake_now = [0.0]

    async def fake_sleep(_):
        fake_now[0] += 2

    result = await _submit_spending_query_impl(
        download_client, toptier_code="068", start_date="2026-01-01", end_date="2026-03-31",
        sleep=fake_sleep, clock=lambda: fake_now[0],
    )
    assert result == {"status": "complete", "file_url": "https://example/job-1.csv", "job_id": "job-1"}


@pytest.mark.asyncio
async def test_submit_returns_pending_when_job_does_not_finish_within_window():
    download_client = AsyncMock()
    download_client.submit_bulk_download.return_value = {"file_name": "job-2"}
    download_client.poll_status.return_value = {"status": "running"}

    fake_now = [0.0]

    async def fake_sleep(_):
        fake_now[0] += 3

    result = await _submit_spending_query_impl(
        download_client, toptier_code="068", start_date="2026-01-01", end_date="2026-03-31",
        poll_window_seconds=MAX_POLL_WINDOW_SECONDS, poll_interval_seconds=3,
        sleep=fake_sleep, clock=lambda: fake_now[0],
    )
    assert result == {"status": "pending", "job_id": "job-2"}


@pytest.mark.asyncio
async def test_submit_returns_failed_status():
    download_client = AsyncMock()
    download_client.submit_bulk_download.return_value = {"file_name": "job-3"}
    download_client.poll_status.return_value = {"status": "failed", "message": "bad filters"}

    result = await _submit_spending_query_impl(
        download_client, toptier_code="068", start_date="2026-01-01", end_date="2026-03-31",
        sleep=AsyncMock(), clock=lambda: 0.0,
    )
    assert result == {"status": "failed", "job_id": "job-3", "message": "bad filters"}


@pytest.mark.asyncio
async def test_get_spending_result_returns_complete():
    download_client = AsyncMock()
    download_client.poll_status.return_value = {"status": "finished", "file_url": "https://example/job-4.csv"}
    result = await _get_spending_result_impl(download_client, job_id="job-4")
    assert result == {"status": "complete", "file_url": "https://example/job-4.csv", "job_id": "job-4"}


@pytest.mark.asyncio
async def test_get_spending_result_returns_pending():
    download_client = AsyncMock()
    download_client.poll_status.return_value = {"status": "running"}
    result = await _get_spending_result_impl(download_client, job_id="job-5")
    assert result == {"status": "pending", "job_id": "job-5"}


@pytest.mark.asyncio
async def test_query_spending_dispatches_submit_bulk_download():
    client = AsyncMock()
    download_client = AsyncMock()
    download_client.submit_bulk_download.return_value = {"file_name": "job-6"}
    download_client.poll_status.return_value = {"status": "finished", "file_url": "https://example/job-6.csv"}
    result = await _query_spending_impl(
        client, download_client, action="submit_bulk_download",
        toptier_code="068", start_date="2026-01-01", end_date="2026-03-31",
    )
    assert result == {"status": "complete", "file_url": "https://example/job-6.csv", "job_id": "job-6"}


@pytest.mark.asyncio
async def test_query_spending_dispatches_get_bulk_download_result():
    client = AsyncMock()
    download_client = AsyncMock()
    download_client.poll_status.return_value = {"status": "running"}
    result = await _query_spending_impl(client, download_client, action="get_bulk_download_result", job_id="job-7")
    assert result == {"status": "pending", "job_id": "job-7"}
