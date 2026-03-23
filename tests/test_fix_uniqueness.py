from incident_commander_env import IncidentCommanderEnv
from incident_commander_env.scenario import load_base_scenarios


def _wrong_mitigation_id(scenario) -> str:
    causal_ids = {mitigation_id for group in scenario.causal_action_sets for mitigation_id in group}
    for mitigation_id in scenario.all_mitigations:
        if mitigation_id not in causal_ids and any(
            rule.mitigation_id == mitigation_id for rule in scenario.mitigation_rules
        ):
            return mitigation_id
    raise AssertionError(f"No wrong mitigation rule available for {scenario.id}")


def test_fix_uniqueness() -> None:
    for scenario in load_base_scenarios():
        env = IncidentCommanderEnv(scenario=scenario)
        env.reset(seed=123)

        wrong_mitigation = _wrong_mitigation_id(scenario)
        actions = [
            {"type": "create_incident", "args": {"title": scenario.title, "severity": scenario.severity}},
            {"type": "apply_mitigation", "args": {"mitigation_id": wrong_mitigation}},
        ]
        actions.extend(
            {"type": rule.action_type, "args": dict(rule.args_match)}
            for rule in scenario.mitigation_rules
            if rule.mitigation_id == wrong_mitigation
        )
        actions.append({"type": "wait", "args": {"steps": 3}})
        actions.extend(
            {
                "type": "confirm_metrics_normalized",
                "args": {
                    "service": requirement.service,
                    "metric": requirement.metric,
                    "target": requirement.target,
                    "window_steps": requirement.window_steps,
                },
            }
            for requirement in scenario.resolution_rubric.required_verification
        )

        done = False
        info = {}
        for action in actions:
            _, _, done, info = env.step(action)
            if done:
                break

        assert env.state is not None
        assert env.state.resolved_state is False, scenario.id
        assert done is False or info.get("resolution") != "success", scenario.id
