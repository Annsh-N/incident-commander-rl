from incident_commander_env import IncidentCommanderEnv, load_replay
from incident_commander_env.replay import replay_summary
from incident_commander_env.scenario import load_base_scenarios


def test_replay_roundtrip(tmp_path) -> None:
    scenario = load_base_scenarios()[0]
    env = IncidentCommanderEnv(scenario=scenario)
    env.reset(seed=321)

    actions = [
        {"type": "create_incident", "args": {"title": scenario.title, "severity": scenario.severity}},
        {"type": "get_logs", "args": {"service": scenario.evidence_markers["deploy_service"], "query": scenario.evidence_markers["key_log_terms"][0].split()[0], "window_steps": 5, "limit": 5, "page": 0}},
        {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Investigating", "eta": "10 minutes"}}},
    ]
    for action in actions:
        env.step(action)

    replay_path = tmp_path / "episode.jsonl"
    env.save_replay(str(replay_path))
    loaded = load_replay(str(replay_path))

    assert loaded == env.get_replay()
    summary = replay_summary(loaded)
    assert summary["scenario_id"] == scenario.id
    assert summary["steps"] == len(loaded)
