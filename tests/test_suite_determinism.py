from incident_commander_env.eval.run_suite import run_agent_on_suite
from incident_commander_env.eval.baselines import HeuristicAgent


def test_suite_determinism(tmp_path) -> None:
    first = run_agent_on_suite(
        agent=HeuristicAgent(),
        seed=77,
        num_variants_per_base=1,
        artifact_dir=str(tmp_path / "first"),
    )
    second = run_agent_on_suite(
        agent=HeuristicAgent(),
        seed=77,
        num_variants_per_base=1,
        artifact_dir=str(tmp_path / "second"),
    )

    assert first == second
    assert 0.3 < first["overall_pass_rate"] < 0.9
