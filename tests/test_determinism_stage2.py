from incident_commander_env import IncidentCommanderEnv


ACTION_SEQUENCE = [
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
        "type": "post_update",
        "args": {
            "audience": "internal",
            "template_id": "initial",
            "fields": {
                "summary": "Investigating checkout failures after deploy.",
                "impact": "Customers cannot complete checkout.",
            },
        },
    },
    {
        "type": "apply_mitigation",
        "args": {"mitigation_id": "disable_new_pricing_path"},
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
        "type": "declare_resolved",
        "args": {
            "root_cause_id": "checkout_pricing_url_misconfigured_after_v42_deploy",
            "mitigation_id": "disable_new_pricing_path",
            "summary": "Disabled the new pricing path and confirmed recovery.",
        },
    },
]


def _run_sequence() -> tuple[list[tuple[int, str, bool]], float, list[dict]]:
    env = IncidentCommanderEnv()
    env.reset(seed=123)
    trajectory: list[tuple[int, str, bool]] = []
    cumulative_reward = 0.0

    for action in ACTION_SEQUENCE:
        obs, reward, done, _ = env.step(action)
        cumulative_reward += reward
        trajectory.append((obs["step"], obs["status"], obs["evidence_flags"]["saw_key_log"]))
        if done:
            break

    return trajectory, cumulative_reward, env.get_replay()


def test_determinism_stage2() -> None:
    first_trajectory, first_reward, first_replay = _run_sequence()
    second_trajectory, second_reward, second_replay = _run_sequence()

    assert first_trajectory == second_trajectory
    assert first_reward == second_reward
    assert first_replay == second_replay
