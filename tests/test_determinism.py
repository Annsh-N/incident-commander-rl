from incident_commander_env import IncidentCommanderEnv


ACTION_SEQUENCE = [
    {"type": "ack_alert", "args": {"alert_id": "alert-checkout-error-rate"}},
    {"type": "get_metrics", "args": {"metric": "error_rate", "window": 3}},
    {
        "type": "get_logs",
        "args": {
            "service": "checkout-service",
            "query": "pricing",
            "limit": 3,
            "page": 1,
        },
    },
    {"type": "view_runbook", "args": {"service": "checkout-service"}},
    {
        "type": "apply_mitigation",
        "args": {"mitigation_id": "rollback_checkout_v42_to_v41"},
    },
    {
        "type": "declare_resolved",
        "args": {
            "root_cause_id": "checkout_pricing_url_misconfigured_after_v42_deploy",
            "mitigation_id": "rollback_checkout_v42_to_v41",
        },
    },
]


def _run_episode() -> tuple[list[tuple[float, int, str]], list[dict]]:
    env = IncidentCommanderEnv()
    env.reset(seed=123)
    trajectory: list[tuple[float, int, str]] = []

    for action in ACTION_SEQUENCE:
        obs, reward, done, _ = env.step(action)
        trajectory.append((reward, obs["step"], obs["status"]))
        if done:
            break

    return trajectory, env.get_replay()


def test_fixed_seed_produces_identical_trajectory_and_replay() -> None:
    first_trajectory, first_replay = _run_episode()
    second_trajectory, second_replay = _run_episode()

    assert first_trajectory == second_trajectory
    assert first_replay == second_replay
