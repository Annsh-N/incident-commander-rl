from incident_commander_env import IncidentCommanderEnv


def test_forbidden_mitigation_penalty() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    _, reward, done, info = env.step(
        {
            "type": "apply_mitigation",
            "args": {"mitigation_id": "restart_database"},
        }
    )

    assert done is False
    assert reward == -0.22
    assert info["unsafe_attempt"] is True
    assert env.state is not None
    assert env.state.unsafe_attempt is True
