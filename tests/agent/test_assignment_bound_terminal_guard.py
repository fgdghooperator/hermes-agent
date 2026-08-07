from agent.assignment_bound_terminal_guard import (
    apply_assignment_terminal_guard,
    normalize_assignment_terminal_response,
)


def test_assignment_complete_gets_exact_final_sentinel():
    response, state = apply_assignment_terminal_guard(
        final_response="All done.",
        messages=[],
        original_user_message="MC-LOCAL-209 assignment-bound validation state: COMPLETE",
    )
    assert state == "COMPLETE"
    assert response == "All done.\n\nCOMPLETE SENTINEL"
    assert response.splitlines()[-1] == "COMPLETE SENTINEL"
    assert response.count("COMPLETE SENTINEL") == 1


def test_assignment_active_blocked_wrong_lane_strip_false_sentinel():
    for state in ["ACTIVE", "BLOCKED", "WRONG_LANE"]:
        response, detected = apply_assignment_terminal_guard(
            final_response=f"{state} — still not complete.\nCOMPLETE SENTINEL",
            messages=[],
            original_user_message=f"MC-LOCAL-209 assignment-bound validation state: {state}",
        )
        assert detected == state
        assert "COMPLETE SENTINEL" not in response


def test_blocked_validation_incomplete_regression_has_no_sentinel():
    response, state = apply_assignment_terminal_guard(
        final_response="BLOCKED — VALIDATION INCOMPLETE\n\nCOMPLETE SENTINEL",
        messages=[],
        original_user_message="MC-LOCAL-209 assignment-bound packet status check",
    )
    assert state == "BLOCKED"
    assert "BLOCKED — VALIDATION INCOMPLETE" in response
    assert "COMPLETE SENTINEL" not in response


def test_commit_gate_required_is_not_complete():
    response, state = apply_assignment_terminal_guard(
        final_response="COMMIT GATE REQUIRED\n\nCOMPLETE SENTINEL",
        messages=[],
        original_user_message="MC-LOCAL-209 assignment-bound implementation packet",
    )
    assert state == "ACTIVE"
    assert "COMPLETE SENTINEL" not in response


def test_non_assignment_response_is_unchanged():
    original = "BLOCKED — VALIDATION INCOMPLETE\n\nCOMPLETE SENTINEL"
    response, state = apply_assignment_terminal_guard(
        final_response=original,
        messages=[],
        original_user_message="general project status",
    )
    assert state is None
    assert response == original


def test_normalize_complete_removes_malformed_duplicate_sentinel():
    assert normalize_assignment_terminal_response(
        "Done\nSENTINEL!!!\nCOMPLETE-SENTINEL",
        "COMPLETE",
    ) == "Done\n\nCOMPLETE SENTINEL"
