from incident_commander_env import IncidentCommanderEnv
from incident_commander_env.cli import main
from incident_commander_env.scenario import load_scenario


def test_cli_entrypoint_smoke(tmp_path) -> None:
    outputs: list[str] = []

    def output_fn(message: str) -> None:
        outputs.append(message)

    play_inputs = iter(
        [
            '{"type":"create_incident","args":{"title":"Demo incident","severity":"sev1"}}',
            "q",
        ]
    )
    play_status = main(
        ["play", "--scenario", "svc-checkout-regression", "--seed", "0", "--out-dir", str(tmp_path / "replays")],
        input_fn=lambda prompt: next(play_inputs),
        output_fn=output_fn,
    )
    assert play_status == 0

    scenario = load_scenario("svc-checkout-regression")
    env = IncidentCommanderEnv(scenario=scenario)
    env.reset(seed=0)
    env.step({"type": "create_incident", "args": {"title": "Replay demo", "severity": "sev1"}})
    replay_path = tmp_path / "sample.jsonl"
    env.save_replay(str(replay_path))

    replay_inputs = iter(["q"])
    replay_status = main(
        ["replay", str(replay_path)],
        input_fn=lambda prompt: next(replay_inputs),
        output_fn=output_fn,
    )
    assert replay_status == 0

    suite_status = main(
        ["suite", "--agent", "heuristic", "--seed", "0", "--variants", "1", "--out", str(tmp_path / "suite")],
        input_fn=lambda prompt: "q",
        output_fn=output_fn,
    )
    assert suite_status == 0
    assert (tmp_path / "suite" / "summary.json").exists()
    assert outputs
