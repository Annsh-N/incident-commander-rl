from incident_commander_env import IncidentCommanderEnv


def test_timeline_messages_arrive_on_expected_steps() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    for _ in range(2):
        obs, _, _, _ = env.step(
            {"type": "get_metrics", "args": {"metric": "error_rate", "window": 1}}
        )

    assert any(
        message["ts_step"] == 2 and "customers can't complete checkout" in message["text"]
        for message in obs["messages"]
    )

    for _ in range(4):
        obs, _, _, _ = env.step(
            {"type": "get_metrics", "args": {"metric": "p95_latency", "window": 1}}
        )

    assert any(
        message["ts_step"] == 6 and "Manager asks for ETA" in message["text"]
        for message in obs["messages"]
    )


def test_valid_mitigation_updates_internal_state() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    _, _, _, info = env.step(
        {
            "type": "apply_mitigation",
            "args": {"mitigation_id": "disable_new_pricing_path"},
        }
    )

    assert info["valid_action"] is True
    assert env.state is not None
    assert env.state.last_mitigation_applied == "disable_new_pricing_path"
