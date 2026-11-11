"""YNAB MCP Server using FastMCP and OpenAPI specification."""

import os
import sys
from importlib.metadata import version

import httpx2
import yaml
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.providers.openapi import MCPType, OpenAPITool, RouteMap
from fastmcp.utilities.openapi import HTTPRoute

YNAB_API_BASE = "https://api.ynab.com/v1"
YNAB_OPENAPI_SPEC_URL = "https://api.ynab.com/papi/open_api_spec.yaml"

# Routes to exclude from the MCP server (these return too much data and bomb the context)
EXCLUDED_ROUTES = [
    RouteMap(
        methods=["GET"],
        pattern=r"^/plans/\{plan_id\}/payees$",
        mcp_type=MCPType.EXCLUDE,
    ),
    RouteMap(
        methods=["GET"],
        pattern=r"^/plans/\{plan_id\}$",
        mcp_type=MCPType.EXCLUDE,
    ),
]

# Transaction lists can run to thousands of entries. These tools all accept
# since_date, until_date, and type, which are the only ways YNAB offers to
# shrink a response.
TRANSACTION_LIST_TOOLS = {
    "getTransactions",
    "getTransactionsByAccount",
    "getTransactionsByCategory",
    "getTransactionsByPayee",
    "getTransactionsByMonth",
}

TRANSACTION_LIST_HINT = (
    "\n\nIMPORTANT: this can return thousands of transactions and overflow your "
    "context. Always pass since_date (and until_date when you know it) covering only "
    "the dates you need, such as the last 7 to 30 days. Without since_date, YNAB "
    'returns a full year. Pass type="unapproved" or type="uncategorized" when '
    "you only need those transactions."
)

MAX_TRANSACTION_LIST_CHARS = 200_000


class TransactionListSizeLimit(Middleware):
    """Reject oversized transaction lists so the model retries with a narrower range."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        result = await call_next(context)
        if context.message.name not in TRANSACTION_LIST_TOOLS:
            return result
        size = sum(len(getattr(block, "text", "")) for block in result.content)
        if size > MAX_TRANSACTION_LIST_CHARS:
            raise ToolError(
                f"The response was too large ({size:,} characters, limit "
                f"{MAX_TRANSACTION_LIST_CHARS:,}). Retry with a narrower "
                "since_date/until_date range or a type filter."
            )
        return result


def _deprecated_operation_ids(openapi_spec: dict) -> set[str]:
    """YNAB keeps deprecated endpoints around as no-ops; don't offer them as tools."""
    return {
        operation["operationId"]
        for path_item in openapi_spec.get("paths", {}).values()
        for operation in path_item.values()
        if isinstance(operation, dict) and operation.get("deprecated")
    }


def _customize_tool(route: HTTPRoute, component: object) -> None:
    if not isinstance(component, OpenAPITool):
        return
    # Cursor rejects some YNAB OpenAPI response schemas; tools do not need them.
    component.output_schema = None
    if route.operation_id in TRANSACTION_LIST_TOOLS:
        component.description = (component.description or "") + TRANSACTION_LIST_HINT


def create_server() -> FastMCP:
    """Create and configure the YNAB MCP server from the OpenAPI spec."""
    token = os.environ.get("YNAB_API_TOKEN")
    if not token:
        raise ValueError(
            "YNAB_API_TOKEN environment variable is required. "
            "Get your personal access token from https://app.ynab.com/settings/developer"
        )

    # Fetch the OpenAPI spec from YNAB
    spec_response = httpx2.get(YNAB_OPENAPI_SPEC_URL)
    spec_response.raise_for_status()
    openapi_spec = yaml.safe_load(spec_response.text)

    # Create an authenticated HTTP client
    client = httpx2.AsyncClient(
        base_url=YNAB_API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )

    deprecated = _deprecated_operation_ids(openapi_spec)

    def exclude_deprecated(route: HTTPRoute, _mcp_type: MCPType) -> MCPType | None:
        return MCPType.EXCLUDE if route.operation_id in deprecated else None

    # Create MCP server from OpenAPI spec
    server = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="YNAB MCP Server",
        version=version("ynab-mcp-tools"),
        route_maps=EXCLUDED_ROUTES,
        route_map_fn=exclude_deprecated,
        mcp_component_fn=_customize_tool,
    )
    server.add_middleware(TransactionListSizeLimit())
    return server


def main() -> None:
    """Run the YNAB MCP server over stdio."""
    try:
        server = create_server()
    except ValueError as e:
        sys.exit(str(e))
    server.run()


if __name__ == "__main__":
    main()
