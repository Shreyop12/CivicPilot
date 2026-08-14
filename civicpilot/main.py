import asyncio
import os

import httpx

from .agent.llm_client import GroqClient
from .agent.orchestrator import Orchestrator
from .cache import QueryCache
from .clients.fr_client import FederalRegisterClient
from .clients.usaspending_client import USASpendingClient
from .clients.usaspending_download_client import USASpendingDownloadClient
from .crosswalk import load_default_crosswalk
from .date_resolver import DateResolver
from .servers.fr_server import build_fr_server
from .servers.usaspending_server import build_usaspending_server


async def build_orchestrator() -> Orchestrator:
    http = httpx.AsyncClient(timeout=30.0)
    cache = QueryCache()

    fr_server = build_fr_server(FederalRegisterClient(http, cache))
    usaspending_server = build_usaspending_server(
        USASpendingClient(http, cache), USASpendingDownloadClient(http),
    )

    llm = GroqClient(http, api_key=os.environ["GROQ_API_KEY"])

    return Orchestrator(
        llm=llm,
        fr_impl=fr_server._search_documents_impl,
        usaspending_impl=usaspending_server._query_spending_impl,
        crosswalk=load_default_crosswalk(),
        date_resolver=DateResolver(),
    )


async def main() -> None:
    orchestrator = await build_orchestrator()
    query = input("Ask CivicPilot: ")
    result = await orchestrator.handle_query(query)
    if result.needs_clarification:
        print(result.clarification_question)
    else:
        print(result.answer)


if __name__ == "__main__":
    asyncio.run(main())
