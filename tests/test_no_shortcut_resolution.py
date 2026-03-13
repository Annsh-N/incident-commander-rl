from incident_commander_env import IncidentCommanderEnv


def test_no_shortcut_resolution() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    env.step(
        {
            "type": "create_incident",
            "args": {"title": "Checkout regression", "severity": "sev1"},
        }
    )
    env.step(
        {
            "type": "get_logs",
            "args": {
                "service": "checkout-service",
                "query": "pricing_url",
                "window_steps": 3,
                "limit": 5,
                "page": 0,
            },
        }
    )
    env.step(
        {
            "type": "apply_mitigation",
            "args": {"mitigation_id": "rollback_checkout_v42_to_v41"},
        }
    )
    obs, reward, done, info = env.step(
        {
            "type": "declare_resolved",
            "args": {
                "root_cause_id": "checkout_pricing_url_misconfigured_after_v42_deploy",
                "mitigation_id": "rollback_checkout_v42_to_v41",
                "summary": "Rolled back checkout.",
            },
        }
    )

    assert done is True
    assert reward < 0.0
    assert info["resolution"] == "unstable"
    assert "no_concrete_change" in info["failure_reasons"]
    assert obs["status"] == "failed"


def test_apply_mitigation_only_proposes_no_system_change() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    env.step(
        {
            "type": "apply_mitigation",
            "args": {"mitigation_id": "revert_pricing_url_config"},
        }
    )

    assert env.state is not None
    assert env.state.proposed_mitigations == ["revert_pricing_url_config"]
    assert env.state.causal_fix_step is None
    assert env.state.resolved_state is False
