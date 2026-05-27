import asyncio
import importlib
import os
import sys
import textwrap
import unittest
from unittest.mock import patch


OPENAPI_SPEC = textwrap.dedent(
    """
    openapi: 3.1.1
    info:
      title: YNAB API Endpoints
      version: 1.84.0
    servers:
      - url: https://api.ynab.com/v1
    paths:
      /plans/{plan_id}/categories:
        post:
          tags:
            - Categories
          summary: Create a category
          operationId: createCategory
          parameters:
            - name: plan_id
              in: path
              required: true
              schema:
                type: string
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  $ref: "#/components/schemas/PostCategoryWrapper"
          responses:
            "201":
              description: The category was successfully created
              content:
                application/json:
                  schema:
                    $ref: "#/components/schemas/SaveCategoryResponse"
      /plans/{plan_id}/payees:
        get:
          tags:
            - Payees
          summary: Get payees
          operationId: getPayees
          parameters:
            - name: plan_id
              in: path
              required: true
              schema:
                type: string
          responses:
            "200":
              description: The payees were returned
              content:
                application/json:
                  schema:
                    type: object
    components:
      schemas:
        PostCategoryWrapper:
          required:
            - category
          type: object
          properties:
            category:
              $ref: "#/components/schemas/NewCategory"
        NewCategory:
          allOf:
            - $ref: "#/components/schemas/SaveCategory"
            - required:
                - name
                - category_group_id
        SaveCategory:
          type: object
          properties:
            name:
              type:
                - string
                - "null"
            note:
              type:
                - string
                - "null"
            category_group_id:
              type: string
              format: uuid
        SaveCategoryResponse:
          required:
            - data
          type: object
          properties:
            data:
              type: object
              required:
                - category
                - server_knowledge
              properties:
                category:
                  type: object
                server_knowledge:
                  type: integer
                  format: int64
    """
)


class SpecResponse:
    text = OPENAPI_SPEC

    def raise_for_status(self) -> None:
        return None


class ServerTests(unittest.TestCase):
    def test_current_plan_category_tool_is_generated_and_large_payees_route_is_excluded(
        self,
    ) -> None:
        sys.modules.pop("ynab_mcp_server.server", None)

        with (
            patch.dict(os.environ, {"YNAB_API_TOKEN": "test-token"}),
            patch("httpx.get", return_value=SpecResponse()),
        ):
            try:
                server = importlib.import_module("ynab_mcp_server.server")
                tools = asyncio.run(server.mcp.list_tools())
            finally:
                sys.modules.pop("ynab_mcp_server.server", None)

        tool_names = {tool.name for tool in tools}
        self.assertIn("createCategory", tool_names)
        self.assertNotIn("getPayees", tool_names)


if __name__ == "__main__":
    unittest.main()
