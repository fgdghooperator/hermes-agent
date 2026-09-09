"""Snapshot-bound native targeting through the real MCP SDK model boundary.

Synthetic public-contract payloads only; no driver, GUI, or runtime startup.
The transport double enforces the relevant cua-driver element-token refusals.
"""
import asyncio
from unittest.mock import AsyncMock

import mcp.types as mcp_types
import pytest

from tools.computer_use.cua_backend import (
    CuaDriverBackend, _CuaDriverSession, _extract_tool_result,
)


class NativeContractTransport:
    def __init__(self):
        self.calls = []
        self.generation = 0
        self.tokens = {}
        self.refusal = None
        self.capture_error = False
        self.emit_tokens = True

    def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "get_window_state":
            if self.capture_error:
                raise RuntimeError("synthetic capture failure")
            self.generation += 1
            token = f"s{self.generation:08x}:1"
            self.tokens = {token: (args["pid"], args["window_id"], 1)}
            element = {"element_index": 1, "role": "AXButton", "label": "Example",
                       "frame": {"x": 10, "y": 10, "w": 80, "h": 30}}
            if self.emit_tokens:
                element["element_token"] = token
            payload = {"snapshot_id": f"s{self.generation:08x}", "elements": [element]}
            error = False
        else:
            code = self.refusal
            if "element_index" in args and not code:
                token = args.get("element_token")
                if not token:
                    code = "snapshot_id_required"
                elif token not in self.tokens:
                    code = "stale_element_token"
                elif self.tokens[token] != (args["pid"], args["window_id"], args["element_index"]):
                    code = "conflicting_element_target"
            error = bool(code)
            payload = ({"status": "refused", "refusal": {"code": code, "message": code}}
                       if code else {"effect": "confirmed"})
        # Exercise the SDK snake_case/camelCase boundary, not a hand-normalized dict.
        return _extract_tool_result(mcp_types.CallToolResult.model_validate({
            "content": [], "isError": error, "structuredContent": payload,
        }))


@pytest.fixture(params=["custom-metadata-preserved", "standard-fields-only"])
def native_backend(monkeypatch, request):
    tools = []
    for name in ("click", "double_click", "scroll", "set_value"):
        tools.append({"name": name, "capabilities": ["accessibility.element_tokens"],
                      "inputSchema": {"type": "object", "properties": {
                          "element_index": {"type": "integer"},
                          "element_token": {"type": "string"},
                          "snapshot_id": {"type": "string"},
                      }}})
    if request.param == "standard-fields-only":
        # MCP 2's Tool discards extension metadata. Model that boundary on
        # MCP 1 test environments too; inputSchema is a standard MCP field.
        for tool in tools:
            tool.pop("capabilities")
    listed = mcp_types.ListToolsResult.model_validate({"tools": tools})
    session = _CuaDriverSession.__new__(_CuaDriverSession)
    asyncio.run(session._populate_capabilities(AsyncMock(list_tools=AsyncMock(return_value=listed))))
    transport = NativeContractTransport()
    monkeypatch.setattr(session, "call_tool", transport.call_tool)
    backend = CuaDriverBackend.__new__(CuaDriverBackend)
    backend._session = session
    backend._session_id = "synthetic-snapshot-session"
    backend._clear_active_target()
    return backend, transport


@pytest.mark.parametrize("action", ["click", "double_click", "right_click", "middle_click", "scroll", "set_value"])
def test_sdk_capture_token_reaches_native_action(native_backend, action):
    backend, transport = native_backend
    captured = backend.capture(mode="som", app="Synthetic", pid=42, window_id=7)
    token = captured.elements[0].element_token
    assert token
    if action == "scroll":
        result = backend.scroll(direction="down", element=1)
    elif action == "set_value":
        result = backend.set_value(value="Example", element=1)
    else:
        result = backend.click(element=1, click_count=2 if action == "double_click" else 1,
                               button={"right_click": "right", "middle_click": "middle"}.get(action, "left"))
    assert result.ok, result
    assert transport.calls[-1][1]["element_token"] == token
    assert transport.calls[-1][1]["window_id"] == 7
    assert transport.calls[-1][1]["pid"] == 42
    assert transport.calls[-1][1]["session"] == "synthetic-snapshot-session"


def test_new_capture_replaces_token_and_exact_target(native_backend):
    backend, transport = native_backend
    first = backend.capture(mode="ax", pid=42, window_id=7).elements[0].element_token
    second = backend.capture(mode="ax", pid=43, window_id=8).elements[0].element_token
    assert first != second
    assert backend.click(element=1).ok
    assert transport.calls[-1][1]["element_token"] == second


@pytest.mark.parametrize("code", ["stale_element_token", "conflicting_element_target", "permission_denied"])
def test_driver_refusal_is_not_retried_or_downgraded(native_backend, code):
    backend, transport = native_backend
    backend.capture(mode="ax", pid=42, window_id=7)
    transport.refusal = code
    result = backend.click(element=1)
    assert not result.ok
    assert result.meta["refusal"]["code"] == code
    assert len(transport.calls) == 2
    assert "x" not in transport.calls[-1][1]


def test_failed_capture_disarms_prior_tokens_and_target(native_backend):
    backend, transport = native_backend
    backend.capture(mode="ax", pid=42, window_id=7)
    transport.capture_error = True
    with pytest.raises(RuntimeError, match="synthetic capture failure"):
        backend.capture(mode="ax", pid=43, window_id=8)
    assert not backend.click(element=1).ok
    assert len(transport.calls) == 2
    assert not backend._snapshot_tokens


def test_tokenless_capture_does_not_reuse_old_token(native_backend):
    backend, transport = native_backend
    backend.capture(mode="ax", pid=42, window_id=7)
    transport.emit_tokens = False
    backend.capture(mode="ax", pid=42, window_id=7)
    assert not backend.click(element=1).ok
    assert "element_token" not in transport.calls[-1][1]


def test_coordinate_action_never_gains_an_element_token(native_backend):
    backend, transport = native_backend
    backend.capture(mode="ax", pid=42, window_id=7)
    assert backend.click(x=10, y=20).ok
    assert "element_token" not in transport.calls[-1][1]


def test_schema_without_token_support_does_not_receive_token(native_backend):
    backend, transport = native_backend
    backend.capture(mode="ax", pid=42, window_id=7)
    backend._session._tool_schemas["click"] = {"properties": {"element_index": {"type": "integer"}}}
    backend._session._capabilities["click"] = set()
    backend.click(element=1)
    assert "element_token" not in transport.calls[-1][1]
