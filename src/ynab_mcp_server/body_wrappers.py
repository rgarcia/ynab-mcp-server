"""Helpers for unwrapping OpenAPI write-body wrappers into flat MCP tool args."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import httpx
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.openapi.director import RequestDirector
from fastmcp.utilities.openapi.models import HTTPRoute, JsonSchema

logger = get_logger(__name__)


def _resolve_schema_refs(schema: JsonSchema, defs: dict[str, Any]) -> JsonSchema:
    """Resolve local $defs refs and merge simple allOf object compositions."""
    if not isinstance(schema, dict):
        return schema

    if "$ref" in schema and isinstance(schema["$ref"], str):
        ref = schema["$ref"]
        if ref.startswith("#/$defs/"):
            resolved = deepcopy(defs.get(ref.split("/")[-1], {}))
            overlay = {k: v for k, v in schema.items() if k != "$ref"}
            if overlay:
                resolved.update(overlay)
            return _resolve_schema_refs(resolved, defs)

    if "allOf" in schema and isinstance(schema["allOf"], list):
        merged: JsonSchema = {k: deepcopy(v) for k, v in schema.items() if k != "allOf"}
        merged_properties: JsonSchema = {}
        merged_required: list[str] = []

        for sub_schema in schema["allOf"]:
            resolved = _resolve_schema_refs(sub_schema, defs)
            if not isinstance(resolved, dict):
                continue

            for key, value in resolved.items():
                if key == "properties" and isinstance(value, dict):
                    merged_properties.update(deepcopy(value))
                elif key == "required" and isinstance(value, list):
                    for item in value:
                        if item not in merged_required:
                            merged_required.append(item)
                elif key not in merged:
                    merged[key] = deepcopy(value)

        if merged_properties:
            merged["type"] = "object"
            merged["properties"] = merged_properties
        if merged_required:
            merged["required"] = merged_required
        return merged

    resolved = deepcopy(schema)
    if "properties" in resolved and isinstance(resolved["properties"], dict):
        resolved["properties"] = {
            key: _resolve_schema_refs(value, defs)
            for key, value in resolved["properties"].items()
        }
    if "items" in resolved and isinstance(resolved["items"], dict):
        resolved["items"] = _resolve_schema_refs(resolved["items"], defs)
    return resolved


def flatten_wrapped_body_parameters(
    parameters: JsonSchema,
    parameter_map: dict[str, dict[str, str]],
) -> tuple[JsonSchema, dict[str, dict[str, str]], bool]:
    """
    Flatten wrapper-shaped body params like `transaction.{...}` into top-level args.

    This avoids MCP clients that degrade nested object parameters into plain strings.
    """
    props = parameters.get("properties")
    defs = parameters.get("$defs", {})
    if not isinstance(props, dict):
        return parameters, parameter_map, False

    body_names = [
        arg_name
        for arg_name, mapping in parameter_map.items()
        if mapping.get("location") == "body"
    ]
    if len(body_names) != 1:
        return parameters, parameter_map, False

    wrapper_name = body_names[0]
    wrapper_schema = props.get(wrapper_name)
    if not isinstance(wrapper_schema, dict):
        return parameters, parameter_map, False

    inner_schema = _resolve_schema_refs(wrapper_schema, defs)
    inner_props = inner_schema.get("properties")
    if inner_schema.get("type") != "object" or not isinstance(inner_props, dict):
        return parameters, parameter_map, False

    flattened = deepcopy(parameters)
    flattened_props = {
        key: value
        for key, value in deepcopy(props).items()
        if key != wrapper_name
    }
    existing_names = set(flattened_props)

    flattened_map = {
        key: deepcopy(value)
        for key, value in parameter_map.items()
        if value.get("location") != "body"
    }
    body_required = []
    inner_required = inner_schema.get("required", [])
    if not isinstance(inner_required, list):
        inner_required = []

    for inner_name, inner_prop_schema in inner_props.items():
        flat_name = inner_name if inner_name not in existing_names else f"{inner_name}__body"
        existing_names.add(flat_name)
        flattened_props[flat_name] = deepcopy(inner_prop_schema)
        flattened_map[flat_name] = {
            "location": "body",
            "openapi_name": f"{wrapper_name}.{inner_name}",
        }
        if inner_name in inner_required:
            body_required.append(flat_name)

    flattened["properties"] = flattened_props
    flattened["required"] = [
        name for name in flattened.get("required", []) if name != wrapper_name
    ]
    for req_name in body_required:
        if req_name not in flattened["required"]:
            flattened["required"].append(req_name)

    return flattened, flattened_map, True


def _set_nested_value(target: dict[str, Any], dotted_name: str, value: Any) -> None:
    """Assign a nested dict value from a dotted path like `transaction.approved`."""
    current = target
    parts = dotted_name.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


class NestedBodyRequestDirector(RequestDirector):
    """RequestDirector that understands dotted body paths for flattened tool args."""

    def _unflatten_arguments(
        self,
        route: HTTPRoute,
        flat_args: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Any]:
        path_params: dict[str, Any] = {}
        query_params: dict[str, Any] = {}
        header_params: dict[str, Any] = {}
        body_props: dict[str, Any] = {}

        if hasattr(route, "parameter_map") and route.parameter_map:
            for arg_name, value in flat_args.items():
                if value is None:
                    continue

                mapping = route.parameter_map.get(arg_name)
                if mapping is None:
                    logger.warning(
                        "Argument '%s' not found in parameter map for %s",
                        arg_name,
                        route.operation_id,
                    )
                    continue

                location = mapping["location"]
                openapi_name = mapping["openapi_name"]

                if location == "path":
                    path_params[openapi_name] = value
                elif location == "query":
                    query_params[openapi_name] = value
                elif location == "header":
                    header_params[openapi_name] = value
                elif location == "body":
                    _set_nested_value(body_props, openapi_name, value)
                else:
                    logger.warning(
                        "Unknown parameter location '%s' for %s",
                        location,
                        arg_name,
                    )
        else:
            return super()._unflatten_arguments(route, flat_args)

        body = body_props or None
        return path_params, query_params, header_params, body


def apply_body_wrapper_fixes(server: Any) -> None:
    """Patch OpenAPI tools in-place so wrapper bodies become flat MCP args."""
    tools = getattr(getattr(server, "_tool_manager", None), "_tools", {})
    nested_director = None

    for tool in tools.values():
        route = getattr(tool, "_route", None)
        if route is None or not getattr(route, "request_body", None):
            continue

        flattened_schema, flattened_map, changed = flatten_wrapped_body_parameters(
            getattr(tool, "parameters", {}),
            getattr(route, "parameter_map", {}),
        )
        if not changed:
            continue

        tool.parameters = flattened_schema
        route.flat_param_schema = flattened_schema
        route.parameter_map = flattened_map

        if nested_director is None:
            nested_director = NestedBodyRequestDirector(tool._director._spec)
        tool._director = nested_director

