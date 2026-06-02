"""MCP tool adapter — converts MCP tool schemas to Haney tool definitions.

MCP tools use JSON Schema for their input schemas. This module
converts those schemas into LiteLLM-compatible function definitions
with namespaced names to avoid collisions with built-in tools.
"""

from __future__ import annotations

from typing import Any

# Namespace prefix for all MCP tools
MCP_TOOL_PREFIX = "mcp__"


def mcp_tool_to_haney_def(
    tool: dict[str, Any],
    server_name: str,
) -> dict[str, Any]:
    """Convert a single MCP tool to a Haney/LiteLLM tool definition.

    Args:
        tool: MCP tool dict with 'name', 'description', and 'inputSchema'.
        server_name: Name of the MCP server (e.g. 'github').

    Returns:
        A LiteLLM-compatible tool definition dict.
    """
    mcp_name = tool.get("name", "unknown")
    # Namespace to prevent collisions: mcp__github__create_issue
    namespaced_name = f"{MCP_TOOL_PREFIX}{server_name}__{mcp_name}"

    description = tool.get("description", f"[{server_name} MCP] {mcp_name}")
    # Prefix description with server info
    full_description = f"[{server_name} MCP] {description}"

    input_schema = tool.get("inputSchema", {})

    # Convert JSON Schema to OpenAI/LiteLLM parameters format
    parameters = _convert_schema_to_params(input_schema)

    return {
        "type": "function",
        "function": {
            "name": namespaced_name,
            "description": full_description,
            "parameters": parameters,
        },
    }


def _convert_schema_to_params(schema: dict) -> dict:
    """Convert a JSON Schema object to LiteLLM parameters format.

    Handles type conversion: JSON Schema uses 'type' as a string,
    LiteLLM expects the full OpenAI function parameters object.

    Args:
        schema: JSON Schema object.

    Returns:
        OpenAI-compatible parameters dict.
    """
    params: dict[str, Any] = {
        "type": schema.get("type", "object"),
    }

    if "properties" in schema:
        params["properties"] = _convert_properties(schema["properties"])

    if "required" in schema:
        params["required"] = schema["required"]

    return params


def _convert_properties(properties: dict) -> dict:
    """Recursively convert JSON Schema properties to LiteLLM format.

    Args:
        properties: JSON Schema properties dict.

    Returns:
        Converted properties dict.
    """
    converted = {}
    for prop_name, prop_schema in properties.items():
        converted[prop_name] = _convert_property(prop_schema)
    return converted


def _convert_property(prop: dict) -> dict:
    """Convert a single JSON Schema property to LiteLLM format.

    Handles nested objects and arrays.

    Args:
        prop: JSON Schema property dict.

    Returns:
        Converted property dict.
    """
    converted: dict[str, Any] = {}

    # Type
    if "type" in prop:
        converted["type"] = prop["type"]

    # Description
    if "description" in prop:
        converted["description"] = prop["description"]

    # Enum values
    if "enum" in prop:
        converted["enum"] = prop["enum"]

    # Nested properties (for object types)
    if "properties" in prop:
        converted["properties"] = _convert_properties(prop["properties"])

    # Required fields for nested objects
    if "required" in prop:
        converted["required"] = prop["required"]

    # Items (for array types)
    if "items" in prop:
        converted["items"] = _convert_property(prop["items"])

    return converted


def parse_tool_name(namespaced_name: str) -> tuple[str, str] | None:
    """Parse a namespaced MCP tool name back into (server, tool).

    Args:
        namespaced_name: Like 'mcp__github__create_issue'.

    Returns:
        Tuple of (server_name, tool_name), or None if not an MCP tool.
    """
    if not namespaced_name.startswith(MCP_TOOL_PREFIX):
        return None

    # Strip prefix
    rest = namespaced_name[len(MCP_TOOL_PREFIX):]
    parts = rest.split("__", 1)

    if len(parts) != 2:
        return None

    return parts[0], parts[1]


def format_tool_result(tool_name: str, result: dict) -> str:
    """Format an MCP tool result for the LLM.

    Args:
        tool_name: Original MCP tool name (without namespace).
        result: Result dict from MCPClient.call_tool().

    Returns:
        Human-readable result string.
    """
    content_items = result.get("content", [])
    is_error = result.get("is_error", False)

    if is_error:
        prefix = f"[{tool_name}] Error:\n"
    else:
        prefix = f"[{tool_name}] Result:\n"

    parts: list[str] = [prefix]

    for item in content_items:
        item_type = item.get("type", "text")

        if item_type == "text":
            parts.append(item.get("text", ""))
        elif item_type == "resource":
            resource = item.get("resource", {})
            parts.append(f"[Resource: {resource.get('uri', 'unknown')}]")
            if "text" in resource:
                parts.append(resource["text"])
        elif item_type == "image":
            parts.append(f"[Image: {item.get('mimeType', 'unknown')}]")
        else:
            parts.append(str(item))

    return "\n".join(parts)
