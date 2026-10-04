"""Unit tests for the probe role -> model table."""

import pytest

from finbot.probe.roles import load_roles


@pytest.mark.unit
def test_committed_roles_cover_agents_and_verifiers():
    roles = load_roles()
    for role in ("orchestrator_agent", "invoice_agent", "fraud_agent",
                 "payments_agent", "communication_agent", "verifier.v3"):
        assert roles.model_for(role) == "openai/gpt-4o-mini-2024-07-18"
    assert roles.model_for("unknown_agent") == roles.default
    assert len(roles.sha256) == 64
