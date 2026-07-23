"""Unit test for the server-info resource (pure, no network)."""

import asyncio
import json

from fastmcp import FastMCP

from src.resources import _VERSION, register_resources


def _read_text(mcp, uri):
    res = asyncio.run(mcp.read_resource(uri))
    return res.contents[0].content


def test_server_info_reads_as_json_with_correct_version():
    # Regression: get_server_info() returned a dict, which FastMCP rejects at
    # read time ("contents must be str, bytes, or list[ResourceContent]"), so
    # the resource listed but was unreadable. It must now read as valid JSON.
    mcp = FastMCP("test")
    register_resources(mcp, reddit=None)  # resource is static; reddit unused

    text = _read_text(mcp, "reddit://server-info")
    data = json.loads(text)  # must parse, not raise

    assert data["name"] == "Reddit Growth MCP"
    # Reports the real installed version, not a drifting hardcoded string.
    assert data["version"] == _VERSION
    assert len(data["tools"]) >= 12
