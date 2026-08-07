from types import SimpleNamespace

import pytest

from agent.bebe_assignment_guard import (
    apply_bebe_assignment_guard,
    determine_bebe_assignment_state,
    normalize_bebe_assignment_response,
)


def bebe_agent():
    return SimpleNamespace(profile="bebe")


def test_complete_appends_exact_single_final_sentinel(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "bebe")
    response, state = apply_bebe_assignment_guard(
        agent=bebe_agent(),
        final_response="Done.\nSENTINEL\nMore text\nCOMPLETE-SENTINEL",
        messages=[{"role": "tool", "name": "kanban_complete", "content": "ok"}],
        original_user_message="MC-LOCAL-209 assignment-bound status check for Bebe",
    )

    assert state == "COMPLETE"
    assert response == "No active assignment-bound work remains.\n\nCOMPLETE SENTINEL"
    assert response.splitlines()[-1] == "COMPLETE SENTINEL"
    assert response.count("COMPLETE SENTINEL") == 1


@pytest.mark.parametrize("state", ["ACTIVE", "BLOCKED", "WRONG_LANE"])
def test_non_complete_states_remove_false_sentinel(monkeypatch, state):
    monkeypatch.setenv("HERMES_PROFILE", "bebe")
    response, detected = apply_bebe_assignment_guard(
        agent=bebe_agent(),
        final_response="Here is code:\n```python\nprint('x')\n```\nCOMPLETE SENTINEL",
        messages=[],
        original_user_message=f"MC-LOCAL-209 Bebe assignment-bound validation\nstate: {state}",
    )

    assert detected == state
    assert "COMPLETE SENTINEL" not in response
    if state == "ACTIVE":
        assert response.startswith("ACTIVE")
    elif state == "BLOCKED":
        assert response.startswith("BLOCKED")
    else:
        assert response.startswith("WRONG_LANE")
        assert "```" not in response
        assert "print(" not in response


def test_no_state_no_change_even_for_bebe(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "bebe")
    original = "The model says maybe done. COMPLETE SENTINEL"
    response, state = apply_bebe_assignment_guard(
        agent=bebe_agent(),
        final_response=original,
        messages=[],
        original_user_message="General Bebe chat with no MC-LOCAL-209 harness state",
    )

    assert state is None
    assert response == original


def test_non_bebe_profile_unchanged(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "jimmy")
    original = "Done without changes"
    response, state = apply_bebe_assignment_guard(
        agent=SimpleNamespace(profile="jimmy"),
        final_response=original,
        messages=[{"role": "tool", "name": "kanban_complete", "content": "ok"}],
        original_user_message="MC-LOCAL-209 assignment-bound status check for Bebe",
    )

    assert state is None
    assert response == original


def test_kanban_block_beats_prompt_complete(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "bebe")
    state = determine_bebe_assignment_state(
        agent=bebe_agent(),
        messages=[{"role": "tool", "name": "kanban_block", "content": "blocked"}],
        original_user_message="MC-LOCAL-209 Bebe assignment-bound validation\nstate: COMPLETE",
    )

    assert state == "BLOCKED"


def test_inline_state_label_is_harness_state(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "bebe")
    response, state = apply_bebe_assignment_guard(
        agent=bebe_agent(),
        final_response="model drift with code ```bad``` COMPLETE SENTINEL",
        messages=[],
        original_user_message="MC-LOCAL-209 Bebe assignment-bound validation. State: COMPLETE. no active work.",
    )

    assert state == "COMPLETE"
    assert response == "No active assignment-bound work remains.\n\nCOMPLETE SENTINEL"


def test_kanban_assignment_without_terminal_tool_is_active(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "bebe")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "MC-LOCAL-209")
    response, state = apply_bebe_assignment_guard(
        agent=bebe_agent(),
        final_response="Looks complete.\nCOMPLETE SENTINEL",
        messages=[],
        original_user_message="MC-LOCAL-209 assignment-bound worker prompt",
    )

    assert state == "ACTIVE"
    assert response.startswith("ACTIVE")
    assert "COMPLETE SENTINEL" not in response


def test_normalize_complete_removes_embedded_malformed_variants():
    assert normalize_bebe_assignment_response(
        "Done. COMPLETE_SENTINEL extra\nSENTINEL!!!\nCOMPLETE-SENTINEL",
        "COMPLETE",
    ) == "No active assignment-bound work remains.\n\nCOMPLETE SENTINEL"
