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


def _last_state_from_matches(matches: Iterable[re.Match[str]]) -> Optional[TerminalState]:
    state: Optional[TerminalState] = None
    for match in matches:
        # A bare/variant COMPLETE SENTINEL line is a marker, not a terminal
        # state label. Treating it as state is the root false-completion class.
        if match.group(1).upper() == "COMPLETE" and "SENTINEL" in match.group(0).upper():
            continue
        state = _normalize_state(match.group(1))
    return state


def _state_from_text(text: str) -> Optional[TerminalState]:
    # Assignment prompts can include quoted historical transcripts before the
    # current harness label. Use the latest explicit label so stale prior
    # ``State: COMPLETE`` text cannot dominate a current BLOCKED/ACTIVE state.
    return _last_state_from_matches(_STATE_RE.finditer(text or ""))


def _state_from_response(text: str) -> Optional[TerminalState]:
    # Same latest-label rule for generated output: if a stale recovered
    # COMPLETE snippet appears before the current BLOCKED/ACTIVE/WRONG_LANE
    # status, the current terminal state wins and the sentinel is stripped.
    # Remove sentinel marker lines before state detection so ``COMPLETE
    # SENTINEL`` cannot be mistaken for a COMPLETE state label.
    text_without_sentinel_lines = "\n".join(
        line for line in (text or "").splitlines() if not _SENTINEL_LINE_RE.match(line)
    )
    return _last_state_from_matches(_RESPONSE_STATE_RE.finditer(text_without_sentinel_lines))


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

    # Harness prompt labels and response labels are both authoritative surfaces.
    # Prefer non-COMPLETE response states over a prompt COMPLETE because that is
    # the observed stale-replay failure mode: old completion text can be present
    # while the current assistant response correctly says BLOCKED/ACTIVE.
    prompt_state = _state_from_text(prompt)
    response_state = _state_from_response(response)
    if response_state in {"ACTIVE", "BLOCKED", "WRONG_LANE"}:
        return response_state
    if prompt_state:
        return prompt_state
    if response_state:
        return response_state
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
