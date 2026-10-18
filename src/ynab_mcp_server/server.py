"""YNAB MCP Server using FastMCP and OpenAPI specification."""

import os

import httpx
import yaml
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.providers.openapi import MCPType, OpenAPITool, RouteMap
from fastmcp.utilities.openapi import HTTPRoute
from mcp.types import ToolAnnotations

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


# Hints that let MCP clients tell read-only tools from ones that change or delete data
TOOL_ANNOTATIONS_BY_METHOD = {
    "GET": ToolAnnotations(readOnlyHint=True),
    "POST": ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    "PUT": ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True),
    "PATCH": ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    "DELETE": ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True),
}


class RequirePathParams(Middleware):
    """Reject tool calls with a missing or blank path ID.

    FastMCP does not validate OpenAPI tool arguments, so a missing ID would otherwise
    be sent to YNAB as a literal "{transaction_id}" or an empty path segment.
    """

    def __init__(self, path_params: dict[str, list[str]]) -> None:
        self.path_params = path_params

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        arguments = context.message.arguments or {}
        missing = [
            name
            for name in self.path_params.get(context.message.name, [])
            if not isinstance(arguments.get(name), str) or not arguments[name].strip()
        ]
        if missing:
            raise ToolError(
                f"{context.message.name} requires a non-empty value for: {', '.join(missing)}"
            )
        return await call_next(context)


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

    path_params: dict[str, list[str]] = {}

    def customize_component(route: HTTPRoute, component: object) -> None:
        if not isinstance(component, OpenAPITool):
            return
        # Cursor rejects some YNAB OpenAPI response schemas; tools do not need them.
        component.output_schema = None
        component.annotations = TOOL_ANNOTATIONS_BY_METHOD.get(route.method.upper())
        path_params[component.name] = [
            param.name for param in route.parameters if param.location == "path"
        ]

    # Create MCP server from OpenAPI spec
    server = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="YNAB MCP Server",
        route_maps=EXCLUDED_ROUTES,
        mcp_component_fn=customize_component,
    )
    server.add_middleware(RequirePathParams(path_params))
    return server


def main() -> None:
    """Run the YNAB MCP server over stdio."""
    create_server().run()


if __name__ == "__main__":
    main()
