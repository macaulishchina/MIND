"""Tests for Phase α-S1: Session Context Accumulation.

Note: α-S1 is **partially unimplemented**.  ``SessionAccessContext`` and the
``session_context`` field on ``AccessRunRequest`` are not yet present (see
audit report).  These tests document the expected behaviour so the feature
can be tracked and verified once implemented.

Covers:
- SessionAccessContext NOT yet in access contracts (regression guard)
- Backward compat: no session_context → normal access behaviour unchanged
"""

from __future__ import annotations

from mind.access.contracts import AccessMode, AccessRunRequest


class TestSessionContextStatus:
    """Document the implementation gap for α-S1."""

    def test_access_run_request_does_not_yet_have_session_context(self) -> None:
        """SessionAccessContext is planned but not yet implemented.

        When α-S1 is complete, this test should be updated to assert the
        field IS present and the companion behavioural tests should be enabled.
        """
        fields = set(AccessRunRequest.model_fields.keys())
        # This assertion documents the current state.  Flip it when the
        # feature is implemented.
        assert "session_context" not in fields, (
            "session_context has been added — update this test and enable "
            "the behavioural tests below."
        )

    def test_access_run_request_backward_compat(self) -> None:
        """Existing callers that do not supply session_context should work."""
        req = AccessRunRequest(
            query="test query",
            task_id="task-1",
            requested_mode=AccessMode.RECALL,
        )
        assert req.query == "test query"
