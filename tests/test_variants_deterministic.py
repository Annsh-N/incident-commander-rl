from incident_commander_env import generate_scenario_suite


def test_variants_deterministic() -> None:
    first_suite = generate_scenario_suite(seed=123, num_variants_per_base=2)
    second_suite = generate_scenario_suite(seed=123, num_variants_per_base=2)

    assert [scenario.id for scenario in first_suite] == [scenario.id for scenario in second_suite]
    assert [scenario.variant_ops for scenario in first_suite] == [scenario.variant_ops for scenario in second_suite]
    assert [scenario.title for scenario in first_suite] == [scenario.title for scenario in second_suite]
