from incident_commander_env import IncidentCommanderEnv


def test_observation_contains_required_keys_and_types() -> None:
    env = IncidentCommanderEnv()
    obs = env.reset(seed=123)

    assert set(obs.keys()) == {
        "step",
        "severity",
        "status",
        "alerts",
        "metrics_snapshot",
        "messages",
        "recent_actions",
        "available_actions",
        "allowed_mitigations",
        "notes",
    }
    assert isinstance(obs["step"], int)
    assert isinstance(obs["severity"], str)
    assert isinstance(obs["alerts"], list)
    assert isinstance(obs["metrics_snapshot"], dict)
    assert isinstance(obs["messages"], list)
    assert isinstance(obs["recent_actions"], list)
    assert isinstance(obs["available_actions"], list)
    assert isinstance(obs["allowed_mitigations"], list)
    assert isinstance(obs["notes"], dict)


def test_available_actions_include_arg_schemas() -> None:
    env = IncidentCommanderEnv()
    obs = env.reset(seed=123)

    action_types = {item["type"]: item for item in obs["available_actions"]}
    assert "get_metrics" in action_types
    assert "arg_schema" in action_types["get_metrics"]
    assert "metric" in action_types["get_metrics"]["arg_schema"]
    assert "window" in action_types["get_metrics"]["arg_schema"]


def test_metrics_snapshot_matches_current_step_values() -> None:
    env = IncidentCommanderEnv()
    obs = env.reset(seed=123)
    scenario = env.scenario

    for metric_name, values in scenario.evidence.metrics_by_step.items():
        assert obs["metrics_snapshot"][metric_name] == float(values[0])
