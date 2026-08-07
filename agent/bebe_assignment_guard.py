"""Bebe-only assignment-bound final response guard.

This module is intentionally narrow. It does not change model/provider routing
or infer completion from model prose. It only normalizes final output when the
runtime/harness supplies an assignment-bound terminal state for Bebe's
MC-LOCAL-209 BUZZ lane.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

TerminalState = Literal["ACTIVE", "BLOCKED", "WRONG_LANE", "COMPLETE"]

_ASSIGNMENT_ID = "MC-LOCAL-209"
_PROFILE_NAME = "bebe"
_SENTINEL = "COMPLETE SENTINEL"
_TERMINAL_KANBAN_TOOL_STATES = {
    "kanban_complete": "COMPLETE",
    "kanban_block": "BLOCKED",
}
_STATE_RE = re.compile(
    r"(?i)\b(?:assignment[-_ ]bound\s+)?(?:terminal\s+)?(?:state|status)\s*[:=]\s*"
    r"(ACTIVE|BLOCKED|WRONG[_ -]?LANE|COMPLETE)\b"
)
_SENTINEL_LINE_RE = re.compile(
    r"(?im)^\s*(?:`{1,3}\s*)?(?:COMPLETE\s*[-_ ]*)?SENTINEL(?:\s*`{1,3})?\s*[.!:,;\-–—]*\s*$"
)
_SENTINEL_INLINE_RE = re.compile(
    r"(?i)\bCOMPLETE\s*[-_ ]+SENTINEL\b"
)
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_TOOL_EXAMPLE_RE = re.compile(
    r"(?im)^\s*(?:write_file|patch|terminal|browser_|computer_use|kanban_complete|kanban_block)\s*\([^\n]*\)\s*$"
)


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(value or "")


def _tool_call_name(tc: Any) -> str:
    if isinstance(tc, dict):
        fn = tc.get("function")
        if isinstance(fn, dict):
            return str(fn.get("name") or "")
        return str(tc.get("name") or "")
    fn = getattr(tc, "function", None)
    if fn is not None:
        return str(getattr(fn, "name", "") or "")
    return str(getattr(tc, "name", "") or "")


def _state_from_messages(messages: Iterable[dict] | None) -> Optional[TerminalState]:
    """Return terminal state recorded by board tools, if any.

    Completion/blocking comes only from the terminal harness tools. The scan is
    order-aware: the latest terminal tool wins if a test double constructs an
    unusual transcript with more than one terminal tool.
    """
    state: Optional[TerminalState] = None
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                maybe = _TERMINAL_KANBAN_TOOL_STATES.get(_tool_call_name(tc))
                if maybe:
                    state = maybe  # type: ignore[assignment]
        elif msg.get("role") == "tool":
            maybe = _TERMINAL_KANBAN_TOOL_STATES.get(str(msg.get("name") or ""))
            if maybe:
                state = maybe  # type: ignore[assignment]
    return state


def _state_from_prompt(original_user_message: Any) -> Optional[TerminalState]:
    """Read explicit assignment-harness state labels from validation prompts.

    This is deliberately not a semantic classifier over arbitrary prose. The
    validation harness must provide a shaped ``state: ...`` / ``status: ...``
    label, and the prompt must be MC-LOCAL-209 assignment-bound context.
    """
    text = _flatten_text(original_user_message)
    if _ASSIGNMENT_ID not in text:
        return None
    if "assignment" not in text.lower() and "bebe" not in text.lower():
        return None
    match = _STATE_RE.search(text)
    if not match:
        return None
    raw = match.group(1).upper().replace("-", "_").replace(" ", "_")
    if raw == "WRONG_LANE":
        return "WRONG_LANE"
    if raw in {"ACTIVE", "BLOCKED", "COMPLETE"}:
        return raw  # type: ignore[return-value]
    return None


def _is_bebe_profile(agent: Any) -> bool:
    env_profile = (os.environ.get("HERMES_PROFILE") or "").strip().lower()
    if env_profile == _PROFILE_NAME:
        return True
    try:
        home = Path(str(os.environ.get("HERMES_HOME") or "")).expanduser()
        if home.name.lower() == _PROFILE_NAME and home.parent.name == "profiles":
            return True
    except Exception:
        pass
    try:
        from hermes_constants import get_hermes_home

        home = get_hermes_home().expanduser()
        if home.name.lower() == _PROFILE_NAME and home.parent.name == "profiles":
            return True
    except Exception:
        pass
    profile = str(getattr(agent, "profile", "") or getattr(agent, "profile_name", "") or "").lower()
    return profile == _PROFILE_NAME


def _is_assignment_context(original_user_message: Any) -> bool:
    task = (os.environ.get("HERMES_KANBAN_TASK") or "").strip()
    if _ASSIGNMENT_ID in task:
        return True
    text = _flatten_text(original_user_message)
    return _ASSIGNMENT_ID in text and ("bebe" in text.lower() or "assignment" in text.lower())


def determine_bebe_assignment_state(
    *,
    agent: Any,
    messages: Iterable[dict] | None,
    original_user_message: Any,
) -> Optional[TerminalState]:
    """Return Bebe MC-LOCAL-209 terminal state from harness/runtime surfaces."""
    if not _is_bebe_profile(agent):
        return None
    if not _is_assignment_context(original_user_message):
        return None
    state = _state_from_messages(messages) or _state_from_prompt(original_user_message)
    if state is not None:
        return state
    task = (os.environ.get("HERMES_KANBAN_TASK") or "").strip()
    if _ASSIGNMENT_ID in task:
        # Dispatcher-spawned assignment worker with no terminal board tool yet:
        # runtime state is active. Do not infer completion from model prose.
        return "ACTIVE"
    return None


def _strip_sentinel_variants(text: str) -> str:
    text = _CODE_FENCE_RE.sub("", text or "")
    lines = [line for line in text.splitlines() if not _SENTINEL_LINE_RE.match(line)]
    text = "\n".join(lines)
    text = _SENTINEL_INLINE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize_bebe_assignment_response(text: str, state: TerminalState) -> str:
    """Mechanically normalize Bebe assignment-bound output for a known state."""
    stripped = _strip_sentinel_variants(text or "")

    if state == "COMPLETE":
        return f"No active assignment-bound work remains.\n\n{_SENTINEL}"

    if state == "ACTIVE":
        # Active validation is status-only; discard code/tool examples from the
        # local model and never emit a completion sentinel.
        return (
            "ACTIVE — MC-LOCAL-209 BUZZ/Bebe assignment-bound work is still active. "
            "No completion sentinel emitted."
        )

    if state == "BLOCKED":
        return (
            "BLOCKED — MC-LOCAL-209 BUZZ/Bebe assignment-bound state reports a blocker. "
            "Resolve the blocker/next gate before completion. No completion sentinel emitted."
        )

    # WRONG_LANE: deterministic reroute/refusal only; no code, tools, commands,
    # destructive guidance, or false completion.
    cleaned = _TOOL_EXAMPLE_RE.sub("", stripped).strip()
    del cleaned  # do not trust model text for wrong-lane terminal contract
    return (
        "WRONG_LANE — This request is outside Bebe/BUZZ/MC-LOCAL-209. "
        "Reroute to the correct owner/lane. No action taken."
    )


def apply_bebe_assignment_guard(
    *,
    agent: Any,
    final_response: Any,
    messages: Iterable[dict] | None,
    original_user_message: Any,
) -> tuple[Any, Optional[TerminalState]]:
    """Apply the narrow Bebe assignment guard; return ``(response, state)``."""
    state = determine_bebe_assignment_state(
        agent=agent,
        messages=messages,
        original_user_message=original_user_message,
    )
    if state is None or not isinstance(final_response, str) or not final_response:
        return final_response, state
    return normalize_bebe_assignment_response(final_response, state), state


__all__ = [
    "apply_bebe_assignment_guard",
    "determine_bebe_assignment_state",
    "normalize_bebe_assignment_response",
]
