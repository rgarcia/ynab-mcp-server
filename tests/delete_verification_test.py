"""Check that deletes YNAB reports but does not apply surface as tool errors, offline."""

import asyncio
import os

import httpx
import yaml
from fastmcp import Client

import ynab_mcp_server.server as server

PATH = "/plans/{plan_id}/scheduled_transactions/{scheduled_transaction_id}"
SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "YNAB", "version": "1"},
    "paths": {
        PATH: {
            "parameters": [
                {"name": "plan_id", "in": "path", "required": True, "schema": {"type": "string"}},
                {"name": "scheduled_transaction_id", "in": "path", "required": True, "schema": {"type": "string"}},
            ],
            "get": {"operationId": "getScheduledTransactionById", "responses": {"200": {"description": "ok"}}},
            "delete": {"operationId": "deleteScheduledTransaction", "responses": {"200": {"description": "ok"}}},
        },
    },
}

# What YNAB returns when the record is fetched after the DELETE, keyed by record ID
AFTER_DELETE = {
    "gone": httpx.Response(404, json={"error": {"id": "404.2", "detail": "Resource not found"}}),
    "ignored": httpx.Response(200, json={"data": {"scheduled_transaction": {"id": "ignored", "deleted": False}}}),
    "flagged": httpx.Response(200, json={"data": {"scheduled_transaction": {"id": "flagged", "deleted": True}}}),
}

sent: list[str] = []


def fake_ynab(request: httpx.Request) -> httpx.Response:
    sent.append(f"{request.method} {request.url.path}")
    record_id = request.url.path.rsplit("/", 1)[-1]
    if request.method == "DELETE":
        # YNAB always claims success, even when it does not apply the delete
        return httpx.Response(200, json={"data": {"scheduled_transaction": {"id": record_id, "deleted": True}}})
    return AFTER_DELETE[record_id]


async def main() -> None:
    os.environ["YNAB_API_TOKEN"] = "test-token"
    server.httpx.get = lambda url: httpx.Response(200, text=yaml.safe_dump(SPEC), request=httpx.Request("GET", url))
    real_client = httpx.AsyncClient
    server.httpx.AsyncClient = lambda **kwargs: real_client(transport=httpx.MockTransport(fake_ynab), **kwargs)

    async with Client(server.create_server()) as client:
        for record_id, should_fail in [("gone", False), ("flagged", False), ("ignored", True)]:
            sent.clear()
            result = await client.call_tool(
                "deleteScheduledTransaction",
                {"plan_id": "plan-1", "scheduled_transaction_id": record_id},
                raise_on_error=False,
            )
            assert result.is_error is should_fail, record_id
            assert sent == [
                f"DELETE /v1/plans/plan-1/scheduled_transactions/{record_id}",
                f"GET /v1/plans/plan-1/scheduled_transactions/{record_id}",
            ], sent
            if should_fail:
                assert "did not delete the record" in result.content[0].text

        sent.clear()
        await client.call_tool("getScheduledTransactionById", {"plan_id": "plan-1", "scheduled_transaction_id": "gone"}, raise_on_error=False)
        assert sent == ["GET /v1/plans/plan-1/scheduled_transactions/gone"], "reads must not trigger a re-fetch"


asyncio.run(main())
print("delete verification checks passed")
