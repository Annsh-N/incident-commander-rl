from incident_commander_env import IncidentCommanderEnv


def test_invalid_action_type_rejected() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    _, reward, _, info = env.step({"type": "page_oncall", "args": {}})

    assert reward == -0.15
    assert info["valid_action"] is False
    assert "unknown action type" in info["error"]


def test_missing_args_rejected() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    _, reward, _, info = env.step({"type": "get_metrics", "args": {"metric": "error_rate"}})

    assert reward == -0.15
    assert info["valid_action"] is False
    assert "missing args" in info["error"]


def test_invalid_metric_name_rejected() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    _, reward, _, info = env.step(
        {"type": "get_metrics", "args": {"metric": "disk_io", "window": 3}}
    )

    assert reward == -0.15
    assert info["valid_action"] is False
    assert "must be one of" in info["error"] or "invalid metric name" in info["error"]


def test_invalid_mitigation_id_rejected() -> None:
    env = IncidentCommanderEnv()
    env.reset(seed=123)

    _, reward, _, info = env.step(
        {"type": "apply_mitigation", "args": {"mitigation_id": "reboot_everything"}}
    )

    assert reward == -0.15
    assert info["valid_action"] is False
    assert "invalid mitigation_id" in info["error"]
