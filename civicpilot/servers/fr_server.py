from mcp.server.fastmcp import FastMCP

from ..clients.fr_client import FederalRegisterClient


async def _search_documents_impl(
    client: FederalRegisterClient,
    *,
    action: str,
    agency_slug: str | None = None,
    doc_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    document_number: str | None = None,
) -> dict:
    if action == "search":
        return await client.search_documents(
            agency_slug=agency_slug, doc_type=doc_type,
            start_date=start_date, end_date=end_date,
        )
    if action == "get":
        if not document_number:
            raise ValueError("document_number is required for action='get'")
        return await client.get_document(document_number)
    raise ValueError(f"unsupported action: {action!r}. Supported actions: 'search', 'get'.")


def build_fr_server(client: FederalRegisterClient) -> FastMCP:
    server = FastMCP("federal-register")

    async def search_documents(
        action: str,
        agency_slug: str | None = None,
        doc_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        document_number: str | None = None,
    ) -> dict:
        """Search or fetch Federal Register documents. action: 'search' or 'get'."""
        return await _search_documents_impl(
            client, action=action, agency_slug=agency_slug, doc_type=doc_type,
            start_date=start_date, end_date=end_date, document_number=document_number,
        )

    server.tool()(search_documents)
    server._search_documents_impl = search_documents
    return server
