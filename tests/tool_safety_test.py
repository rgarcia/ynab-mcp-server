"""Check tool annotations and path ID validation offline, against a mocked YNAB API."""

import asyncio
import os

import httpx
import yaml
from fastmcp import Client

import ynab_mcp_server.server as server

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "YNAB", "version": "1"},
    "paths": {
        "/plans/{plan_id}/transactions/{transaction_id}": {
            "parameters": [
                {"name": "plan_id", "in": "path", "required": True, "schema": {"type": "string"}},
                {"name": "transaction_id", "in": "path", "required": True, "schema": {"type": "string"}},
            ],
            "get": {"operationId": "getTransactionById", "responses": {"200": {"description": "ok"}}},
            "delete": {"operationId": "deleteTransaction", "responses": {"200": {"description": "ok"}}},
        },
        "/plans/{plan_id}/transactions": {
            "parameters": [
                {"name": "plan_id", "in": "path", "required": True, "schema": {"type": "string"}},
            ],
            "post": {"operationId": "createTransaction", "responses": {"201": {"description": "ok"}}},
        },
    },
}

sent: list[httpx.Request] = []


def fake_ynab(request: httpx.Request) -> httpx.Response:
    sent.append(request)
    return httpx.Response(200, json={"data": {}})


async def main() -> None:
    os.environ["YNAB_API_TOKEN"] = "test-token"
    server.httpx.get = lambda url: httpx.Response(200, text=yaml.safe_dump(SPEC), request=httpx.Request("GET", url))
    real_client = httpx.AsyncClient
    server.httpx.AsyncClient = lambda **kwargs: real_client(transport=httpx.MockTransport(fake_ynab), **kwargs)

    async with Client(server.create_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert tools["getTransactionById"].annotations.readOnlyHint is True
        assert tools["createTransaction"].annotations.destructiveHint is False
        assert tools["deleteTransaction"].annotations.readOnlyHint is False
        assert tools["deleteTransaction"].annotations.destructiveHint is True

        for arguments in [
            {"plan_id": "plan-1"},
            {"plan_id": "plan-1", "transaction_id": ""},
            {"plan_id": "  ", "transaction_id": "t1"},
        ]:
            result = await client.call_tool("deleteTransaction", arguments, raise_on_error=False)
            assert result.is_error, arguments
            assert "requires a non-empty value" in result.content[0].text
        assert not sent, "invalid calls must not reach YNAB"

        result = await client.call_tool("deleteTransaction", {"plan_id": "plan-1", "transaction_id": "t1"})
        assert not result.is_error
        assert [(r.method, r.url.path) for r in sent] == [
            ("DELETE", "/v1/plans/plan-1/transactions/t1"),
            ("GET", "/v1/plans/plan-1/transactions/t1"),  # VerifyDeletes re-fetch
        ]


asyncio.run(main())
print("tool safety checks passed")
