from incident_commander_env import IncidentCommanderEnv


def test_success_path_stage2() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    actions = [
        {
            "type": "create_incident",
            "args": {"title": "Checkout regression", "severity": "sev1"},
        },
        {
            "type": "get_metrics",
            "args": {
                "service": "checkout-service",
                "metric": "error_rate",
                "window_steps": 1,
                "agg": "raw",
            },
        },
        {
            "type": "get_logs",
            "args": {
                "service": "checkout-service",
                "query": "pricing_url",
                "window_steps": 3,
                "limit": 5,
                "page": 0,
            },
        },
        {
            "type": "post_update",
            "args": {
                "audience": "internal",
                "template_id": "initial",
                "fields": {
                    "summary": "Checkout failures under investigation after recent deploy.",
                    "impact": "Customers unable to complete checkout.",
                },
            },
        },
        {
            "type": "search_recent_deploys",
            "args": {"service": "checkout-service", "window_steps": 5},
        },
        {
            "type": "diff_config",
            "args": {
                "service": "checkout-service",
                "from_version": "v41",
                "to_version": "v42",
            },
        },
        {
            "type": "apply_mitigation",
            "args": {"mitigation_id": "revert_pricing_url_config"},
        },
        {
            "type": "apply_config_patch",
            "args": {
                "service": "checkout-service",
                "patch_id": "fix_pricing_url_v42",
            },
        },
        {"type": "wait", "args": {"steps": 1}},
        {
            "type": "confirm_metrics_normalized",
            "args": {
                "service": "checkout-service",
                "metric": "error_rate",
                "target": 2.5,
                "window_steps": 1,
            },
        },
        {
            "type": "confirm_metrics_normalized",
            "args": {
                "service": "checkout-service",
                "metric": "p95_latency",
                "target": 700.0,
                "window_steps": 1,
            },
        },
        {
            "type": "post_update",
            "args": {
                "audience": "internal",
                "template_id": "status",
                "fields": {
                    "summary": "Applied mitigation and metrics are recovering.",
                    "eta": "5 minutes",
                },
            },
        },
        {
            "type": "declare_resolved",
            "args": {
                "root_cause_id": "checkout_pricing_url_misconfigured_after_v42_deploy",
                "mitigation_id": "revert_pricing_url_config",
                "summary": "Corrected malformed PRICING_URL and confirmed recovery.",
            },
        },
    ]

    cumulative_reward = 0.0
    done = False
    info = {}
    obs = {}
    for action in actions:
        obs, reward, done, info = env.step(action)
        cumulative_reward += reward
        if done:
            break

    assert done is True
    assert info["resolution"] == "success"
    assert obs["status"] == "resolved"
    assert obs["evidence_flags"]["saw_key_log"] is True
    assert obs["evidence_flags"]["saw_deploy"] is True
    assert obs["evidence_flags"]["saw_config_diff"] is True
    assert cumulative_reward > 1.0
