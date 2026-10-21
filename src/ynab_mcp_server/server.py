"""YNAB MCP Server using FastMCP and OpenAPI specification."""

import os
from urllib.parse import quote

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


class VerifyDeletes(Middleware):
    """Re-fetch a record after deleting it, and fail if YNAB did not actually delete it.

    YNAB sometimes answers a DELETE with HTTP 200 and "deleted": true without applying
    it: server_knowledge does not change and the record is still returned afterwards.
    """

    def __init__(self, client: httpx.AsyncClient, delete_paths: dict[str, str]) -> None:
        self.client = client
        self.delete_paths = delete_paths

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        result = await call_next(context)
        path_template = self.delete_paths.get(context.message.name)
        if path_template is None:
            return result

        arguments = context.message.arguments or {}
        path = path_template.format_map(
            {name: quote(str(value), safe="") for name, value in arguments.items()}
        )
        try:
            response = await self.client.get(path)
        except httpx.HTTPError as e:
            raise ToolError(
                f"YNAB accepted the delete, but checking that it applied failed "
                f"({type(e).__name__}). Fetch the record to confirm it is gone."
            ) from e
        if response.status_code == 404:
            return result
        if response.status_code != 200:
            raise ToolError(
                f"YNAB accepted the delete, but checking that it applied returned "
                f"HTTP {response.status_code}. Fetch the record to confirm it is gone."
            )
        records = [
            value
            for value in response.json().get("data", {}).values()
            if isinstance(value, dict) and "deleted" in value
        ]
        if records and records[0]["deleted"] is False:
            raise ToolError(
                f"YNAB returned success for {context.message.name} but did not delete the "
                f"record: it is still present with deleted=false. Delete it in the YNAB app "
                f"instead."
            )
        return result


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
    delete_paths: dict[str, str] = {}

    def customize_component(route: HTTPRoute, component: object) -> None:
        if not isinstance(component, OpenAPITool):
            return
        # Cursor rejects some YNAB OpenAPI response schemas; tools do not need them.
        component.output_schema = None
        component.annotations = TOOL_ANNOTATIONS_BY_METHOD.get(route.method.upper())
        path_params[component.name] = [
            param.name for param in route.parameters if param.location == "path"
        ]
        if route.method.upper() == "DELETE":
            delete_paths[component.name] = route.path

    # Create MCP server from OpenAPI spec
    server = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="YNAB MCP Server",
        route_maps=EXCLUDED_ROUTES,
        mcp_component_fn=customize_component,
    )
    server.add_middleware(RequirePathParams(path_params))
    server.add_middleware(VerifyDeletes(client, delete_paths))
    return server


def main() -> None:
    """Run the YNAB MCP server over stdio."""
    create_server().run()


if __name__ == "__main__":
    main()
