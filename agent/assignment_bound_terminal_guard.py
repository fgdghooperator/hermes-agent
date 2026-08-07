"""Shared MC-LOCAL-209 assignment-bound terminal-state guard.

This guard is intentionally narrow: it only applies when MC-LOCAL-209 /
assignment-bound context is explicit in the user/harness prompt or response. It
prevents false completion sentinels in ACTIVE, BLOCKED, and WRONG_LANE terminal
states across profiles, while allowing the exact sentinel only for explicit
COMPLETE state.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal, Optional

TerminalState = Literal["ACTIVE", "BLOCKED", "WRONG_LANE", "COMPLETE"]

_ASSIGNMENT_ID = "MC-LOCAL-209"
_SENTINEL = "COMPLETE SENTINEL"
_STATE_RE = re.compile(
    r"(?i)\b(?:assignment[-_ ]bound\s+)?(?:terminal\s+)?(?:state|status|classification)\s*[:=]\s*"
    r"(ACTIVE|BLOCKED|WRONG[_ -]?LANE|COMPLETE|COMMIT\s+GATE\s+REQUIRED)\b"
)
_RESPONSE_STATE_RE = re.compile(
    r"(?im)^\s*(ACTIVE|BLOCKED|WRONG[_ -]?LANE|COMPLETE|COMMIT\s+GATE\s+REQUIRED)\b"
)
_SENTINEL_LINE_RE = re.compile(
    r"(?im)^\s*(?:`{1,3}\s*)?(?:COMPLETE\s*[-_ ]*)?SENTINEL(?:\s*`{1,3})?\s*[.!:,;\-–—]*\s*$"
)
_SENTINEL_INLINE_RE = re.compile(r"(?i)\bCOMPLETE\s*[-_ ]+SENTINEL\b")
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")


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


def _normalize_state(raw: str) -> TerminalState:
    value = raw.upper().replace("-", "_").replace(" ", "_")
    if value == "WRONG_LANE":
        return "WRONG_LANE"
    if value == "COMMIT_GATE_REQUIRED":
        # Commit gates are unresolved approval gates, not complete terminal state.
        return "ACTIVE"
    if value in {"ACTIVE", "BLOCKED", "COMPLETE"}:
        return value  # type: ignore[return-value]
    return "ACTIVE"


def _state_from_text(text: str) -> Optional[TerminalState]:
    match = _STATE_RE.search(text or "")
    if match:
        return _normalize_state(match.group(1))
    return None


def _state_from_response(text: str) -> Optional[TerminalState]:
    match = _RESPONSE_STATE_RE.search(text or "")
    if match:
        return _normalize_state(match.group(1))
    return None


def _strip_sentinel_variants(text: str) -> str:
    # Drop code fences first so example sentinels cannot survive as evidence.
    text = _CODE_FENCE_RE.sub("", text or "")
    lines = [line for line in text.splitlines() if not _SENTINEL_LINE_RE.match(line)]
    text = "\n".join(lines)
    text = _SENTINEL_INLINE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def determine_assignment_terminal_state(
    *,
    messages: Iterable[dict] | None,
    original_user_message: Any,
    final_response: Any,
) -> Optional[TerminalState]:
    """Return explicit assignment terminal state, if the turn supplies one."""
    prompt = _flatten_text(original_user_message)
    response = _flatten_text(final_response)
    combined = f"{prompt}\n{response}"
    if _ASSIGNMENT_ID not in combined or "assignment" not in combined.lower():
        return None

    # Harness prompt labels are authoritative. Response labels catch the exact
    # regression class where the assistant says BLOCKED/ACTIVE then appends a
    # false completion sentinel.
    state = _state_from_text(prompt)
    if state:
        return state
    state = _state_from_response(response)
    if state:
        return state
    return None


def normalize_assignment_terminal_response(text: str, state: TerminalState) -> str:
    cleaned = _strip_sentinel_variants(text or "")
    if state == "COMPLETE":
        body = cleaned or "No active assignment-bound work remains."
        return f"{body}\n\n{_SENTINEL}"
    if state in {"ACTIVE", "BLOCKED", "WRONG_LANE"}:
        return cleaned
    return cleaned


def apply_assignment_terminal_guard(
    *,
    final_response: Any,
    messages: Iterable[dict] | None,
    original_user_message: Any,
) -> tuple[Any, Optional[TerminalState]]:
    state = determine_assignment_terminal_state(
        messages=messages,
        original_user_message=original_user_message,
        final_response=final_response,
    )
    if state is None or not isinstance(final_response, str) or not final_response:
        return final_response, state
    return normalize_assignment_terminal_response(final_response, state), state


__all__ = [
    "apply_assignment_terminal_guard",
    "determine_assignment_terminal_state",
    "normalize_assignment_terminal_response",
]
