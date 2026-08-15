import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

from .agent.llm_client import FailoverLLMClient, GroqClient, OpenRouterClient
from .agent.orchestrator import Orchestrator
from .cache import QueryCache
from .clients.fr_client import FederalRegisterClient
from .clients.usaspending_client import USASpendingClient
from .clients.usaspending_download_client import USASpendingDownloadClient
from .crosswalk import AgencyCrosswalk, load_default_crosswalk
from .date_resolver import DateResolver
from .servers.fr_server import build_fr_server
from .servers.usaspending_server import build_usaspending_server


@dataclass
class AppComponents:
    orchestrator: Orchestrator
    http: httpx.AsyncClient
    fr_impl: Callable[..., Awaitable[dict]]
    usaspending_impl: Callable[..., Awaitable[dict]]
    crosswalk: AgencyCrosswalk


async def build_orchestrator() -> AppComponents:
    load_dotenv()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY environment variable is not set")
        raise SystemExit(1)

    http = httpx.AsyncClient(timeout=30.0)
    cache = QueryCache()

    fr_server = build_fr_server(FederalRegisterClient(http, cache))
    usaspending_server = build_usaspending_server(
        USASpendingClient(http, cache), USASpendingDownloadClient(http),
    )

    primary_llm = GroqClient(http, api_key=api_key)
    fallback_api_key = os.environ.get("OPENROUTER_API_KEY")
    if fallback_api_key:
        llm = FailoverLLMClient(primary_llm, OpenRouterClient(http, api_key=fallback_api_key))
    else:
        logging.getLogger(__name__).warning(
            "OPENROUTER_API_KEY not set — no fallback LLM configured; a Groq "
            "outage or rate limit will fail the whole query."
        )
        llm = primary_llm

    crosswalk = load_default_crosswalk()
    orchestrator = Orchestrator(
        llm=llm,
        fr_impl=fr_server._search_documents_impl,
        usaspending_impl=usaspending_server._query_spending_impl,
        crosswalk=crosswalk,
        date_resolver=DateResolver(),
    )
    return AppComponents(
        orchestrator=orchestrator,
        http=http,
        fr_impl=fr_server._search_documents_impl,
        usaspending_impl=usaspending_server._query_spending_impl,
        crosswalk=crosswalk,
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    components = await build_orchestrator()
    try:
        query = input("Ask CivicPilot: ")
        result = await components.orchestrator.handle_query(query)
        if result.needs_clarification:
            print(result.clarification_question)
        else:
            print(result.answer)
    finally:
        await components.http.aclose()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
