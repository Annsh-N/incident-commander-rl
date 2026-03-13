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
            "type": "post_update",
            "args": {
                "audience": "internal",
                "template_id": "initial",
                "fields": {
                    "summary": "Investigating checkout failures.",
                    "impact": "Checkout unavailable.",
                },
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
    assert obs["status"] == "failed"
