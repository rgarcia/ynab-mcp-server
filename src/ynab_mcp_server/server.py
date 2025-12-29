"""YNAB MCP Server using FastMCP and OpenAPI specification."""

import os

import httpx
import yaml
from fastmcp import FastMCP
from fastmcp.server.openapi import MCPType, RouteMap

YNAB_API_BASE = "https://api.ynab.com/v1"
YNAB_OPENAPI_SPEC_URL = "https://api.ynab.com/papi/open_api_spec.yaml"

# Routes to exclude from the MCP server (these return too much data and bomb the context)
EXCLUDED_ROUTES = [
    RouteMap(
        methods=["GET"],
        pattern=r"^/budgets/\{budget_id\}/payees$",
        mcp_type=MCPType.EXCLUDE,
    ),
]


def create_server() -> FastMCP:
    """Create and configure the YNAB MCP server from the OpenAPI spec."""
    token = os.environ.get("YNAB_API_TOKEN")
    if not token:
        raise ValueError(
            "YNAB_API_TOKEN environment variable is required. "
            "Get your personal access token from https://app.ynab.com/settings/developer"
        )

    # Fetch the OpenAPI spec from YNAB
    spec_response = httpx.get(YNAB_OPENAPI_SPEC_URL)
    spec_response.raise_for_status()
    openapi_spec = yaml.safe_load(spec_response.text)

    # Create an authenticated HTTP client
    client = httpx.AsyncClient(
        base_url=YNAB_API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )

    # Create MCP server from OpenAPI spec
    return FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="YNAB MCP Server",
        route_maps=EXCLUDED_ROUTES,
    )


mcp = create_server()

if __name__ == "__main__":
    mcp.run()
