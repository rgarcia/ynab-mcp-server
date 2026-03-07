"""Regression tests for wrapped OpenAPI request bodies."""

from __future__ import annotations

import unittest

from jsonschema_path import SchemaPath

from fastmcp.utilities.openapi.models import HTTPRoute, RequestBodyInfo
from ynab_mcp_server.body_wrappers import (
    NestedBodyRequestDirector,
    flatten_wrapped_body_parameters,
)


class BodyWrapperTests(unittest.TestCase):
    def test_flatten_wrapped_transaction_object(self) -> None:
        parameters = {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "transaction_id": {"type": "string"},
                "transaction": {"$ref": "#/$defs/ExistingTransaction"},
            },
            "required": ["plan_id", "transaction_id", "transaction"],
            "$defs": {
                "ExistingTransaction": {
                    "allOf": [
                        {"type": "object"},
                        {"$ref": "#/$defs/SaveTransactionWithOptionalFields"},
                    ]
                },
                "SaveTransactionWithOptionalFields": {
                    "type": "object",
                    "properties": {
                        "approved": {"type": "boolean"},
                        "memo": {"type": ["string", "null"]},
                    },
                    "required": ["approved"],
                },
            },
        }
        parameter_map = {
            "plan_id": {"location": "path", "openapi_name": "plan_id"},
            "transaction_id": {"location": "path", "openapi_name": "transaction_id"},
            "transaction": {"location": "body", "openapi_name": "transaction"},
        }

        flattened, flattened_map, changed = flatten_wrapped_body_parameters(
            parameters,
            parameter_map,
        )

        self.assertTrue(changed)
        self.assertNotIn("transaction", flattened["properties"])
        self.assertIn("approved", flattened["properties"])
        self.assertIn("memo", flattened["properties"])
        self.assertIn("approved", flattened["required"])
        self.assertEqual(
            flattened_map["approved"],
            {"location": "body", "openapi_name": "transaction.approved"},
        )

    def test_nested_director_rewraps_flattened_args(self) -> None:
        route = HTTPRoute(
            path="/plans/{plan_id}/transactions/{transaction_id}",
            method="PUT",
            operation_id="updateTransaction",
            parameter_map={
                "plan_id": {"location": "path", "openapi_name": "plan_id"},
                "transaction_id": {"location": "path", "openapi_name": "transaction_id"},
                "approved": {"location": "body", "openapi_name": "transaction.approved"},
                "memo": {"location": "body", "openapi_name": "transaction.memo"},
            },
            request_body=RequestBodyInfo(
                required=True,
                content_schema={
                    "application/json": {
                        "type": "object",
                        "properties": {
                            "transaction": {
                                "type": "object",
                                "properties": {
                                    "approved": {"type": "boolean"},
                                    "memo": {"type": "string"},
                                },
                            }
                        },
                    }
                },
            ),
        )

        director = NestedBodyRequestDirector(SchemaPath.from_dict({"openapi": "3.1.0"}))
        path_params, query_params, header_params, body = director._unflatten_arguments(
            route,
            {
                "plan_id": "plan-1",
                "transaction_id": "txn-1",
                "approved": True,
                "memo": "looks good",
            },
        )

        self.assertEqual(path_params, {"plan_id": "plan-1", "transaction_id": "txn-1"})
        self.assertEqual(query_params, {})
        self.assertEqual(header_params, {})
        self.assertEqual(
            body,
            {"transaction": {"approved": True, "memo": "looks good"}},
        )


if __name__ == "__main__":
    unittest.main()
