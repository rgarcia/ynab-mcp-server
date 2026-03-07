"""YNAB MCP Server using FastMCP and OpenAPI specification."""

import os
from collections.abc import Mapping
from typing import Any

import httpx
import yaml
from fastmcp import FastMCP
from fastmcp.server.openapi import MCPType, RouteMap

from ynab_mcp_server.body_wrappers import apply_body_wrapper_fixes

YNAB_API_BASE = "https://api.ynab.com/v1"
YNAB_OPENAPI_SPEC_URL = "https://api.ynab.com/papi/open_api_spec.yaml"

# Routes to exclude from the MCP server when they are known to produce
# payloads large enough to destabilize clients.
EXCLUDED_ROUTES = [
    RouteMap(
        methods=["GET"],
        pattern=r"^/plans/\{plan_id\}$",
        mcp_type=MCPType.EXCLUDE,
    ),
    RouteMap(
        methods=["GET"],
        pattern=r"^/plans/\{plan_id\}/payees$",
        mcp_type=MCPType.EXCLUDE,
    ),
]


def _normalize_nullable_schema(node: Any) -> Any:
    """Fix YNAB OpenAPI fragments that use nullable without an explicit type."""
    if isinstance(node, list):
        return [_normalize_nullable_schema(item) for item in node]

    if not isinstance(node, dict):
        return node

    normalized = {
        key: _normalize_nullable_schema(value)
        for key, value in node.items()
    }

    if (
        normalized.get("nullable") is True
        and "type" not in normalized
        and "oneOf" not in normalized
        and "anyOf" not in normalized
    ):
        inner = {key: value for key, value in normalized.items() if key != "nullable"}
        return {"anyOf": [inner, {"type": "null"}]}

    return normalized


def _normalize_openapi_spec(openapi_spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return a FastMCP-compatible copy of the upstream YNAB OpenAPI spec."""
    return _normalize_nullable_schema(dict(openapi_spec))


def create_server() -> FastMCP:
    """Create and configure the YNAB MCP server from the OpenAPI spec."""
    token = os.environ.get("YNAB_API_TOKEN")
    if not token:
        raise ValueError(
            "YNAB_API_TOKEN environment variable is required. "
            "Get your personal access token from https://app.ynab.com/settings/developer"
        )

    # Fetch the OpenAPI spec from YNAB
    spec_response = httpx.get(YNAB_OPENAPI_SPEC_URL, timeout=30.0)
    spec_response.raise_for_status()
    openapi_spec = _normalize_openapi_spec(yaml.safe_load(spec_response.text))

    # Create an authenticated HTTP client
    client = httpx.AsyncClient(
        base_url=YNAB_API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )

    # Create MCP server from OpenAPI spec
    server = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="YNAB MCP Server",
        route_maps=EXCLUDED_ROUTES,
    )
    apply_body_wrapper_fixes(server)
    return server


mcp = create_server()

if __name__ == "__main__":
    mcp.run()
