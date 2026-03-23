from incident_commander_env import IncidentCommanderEnv, generate_scenario_suite
from incident_commander_env.scenario import load_base_scenarios


def _key_log_service(scenario):
    for service, entries in scenario.evidence.logs_by_service.items():
        if any(
            any(term.casefold() in entry.message.casefold() for term in scenario.evidence_markers["key_log_terms"])
            for entry in entries
        ):
            return service
    return next(iter(scenario.evidence.logs_by_service.keys()))


def _key_log_query(scenario) -> str:
    log_service = _key_log_service(scenario)
    messages = [entry.message.casefold() for entry in scenario.evidence.logs_by_service[log_service]]
    for term in scenario.evidence_markers["key_log_terms"]:
        if any(term.casefold() in message for message in messages):
            return term
    return scenario.evidence_markers["key_log_terms"][0]


def _resolve_with_metadata(scenario):
    env = IncidentCommanderEnv(scenario=scenario)
    env.reset(seed=999)

    first_diff = scenario.evidence.config_diffs[0] if scenario.evidence.config_diffs else None
    log_service = _key_log_service(scenario)
    actions = [
        {"type": "create_incident", "args": {"title": scenario.title, "severity": scenario.severity}},
        {
            "type": "post_update",
            "args": {
                "audience": "internal",
                "template_id": "status",
                "fields": {"summary": "Mitigation in progress", "eta": "10 minutes"},
            },
        },
    ]

    for requirement in scenario.resolution_rubric.required_verification:
        actions.append(
            {
                "type": "get_metrics",
                "args": {
                    "service": requirement.service,
                    "metric": requirement.metric,
                    "window_steps": 1,
                    "agg": "raw",
                },
            }
        )

    actions.append({"type": "wait", "args": {"steps": 2}})
    actions.append(
        {
            "type": "get_logs",
            "args": {
                "service": log_service,
                "query": _key_log_query(scenario),
                "window_steps": 25,
                "limit": 10,
                "page": 0,
            },
        }
    )

    if scenario.evidence.deploy_history:
        deploy_service = scenario.evidence_markers["deploy_service"]
        actions.append(
            {
                "type": "search_recent_deploys",
                "args": {"service": deploy_service, "window_steps": 25},
            }
        )
    if first_diff is not None:
        actions.append(
            {
                "type": "diff_config",
                "args": {
                    "service": first_diff.service,
                    "from_version": first_diff.from_version,
                    "to_version": first_diff.to_version,
                },
            }
        )
    if "saw_timeout_trace" in scenario.resolution_rubric.required_evidence_flags:
        trace = next(
            sample
            for sample in scenario.evidence.trace_samples
            if sample.error
            and any(
                term.casefold() in sample.error.casefold()
                for term in scenario.evidence_markers.get("trace_error_terms", [])
            )
        )
        actions.append(
            {"type": "get_trace_sample", "args": {"service": trace.service, "trace_id": trace.trace_id}}
        )
    if "saw_runbook" in scenario.resolution_rubric.required_evidence_flags:
        runbook_service = next(iter(scenario.evidence.runbook_snippets.keys()))
        actions.append({"type": "view_runbook", "args": {"service": runbook_service, "section": "triage"}})

    mitigation_id = scenario.allowed_mitigations[0]
    actions.append({"type": "apply_mitigation", "args": {"mitigation_id": mitigation_id}})
    for rule in scenario.mitigation_rules:
        if rule.causal and rule.mitigation_id == mitigation_id:
            actions.append({"type": rule.action_type, "args": dict(rule.args_match)})

    actions.append({"type": "wait", "args": {"steps": 3}})
    for requirement in scenario.resolution_rubric.required_verification:
        actions.append(
            {
                "type": "confirm_metrics_normalized",
                "args": {
                    "service": requirement.service,
                    "metric": requirement.metric,
                    "target": requirement.target,
                    "window_steps": requirement.window_steps,
                },
            }
        )

    for requirement in scenario.resolution_rubric.required_updates:
        if requirement.template_id == "status" and requirement.audience == "internal":
            continue
        fields = {"summary": "Recovered", "customer_impact": "Resolved"}
        if requirement.template_id == "status":
            fields = {"summary": "Recovered", "eta": "0 minutes"}
        actions.append(
            {
                "type": "post_update",
                "args": {
                    "audience": requirement.audience,
                    "template_id": requirement.template_id,
                    "fields": fields,
                },
            }
        )

    actions.append(
        {
            "type": "declare_resolved",
            "args": {
                "root_cause_id": scenario.ground_truth_root_cause_id,
                "mitigation_id": mitigation_id,
                "summary": "Resolved with scenario-aware test helper",
            },
        }
    )

    info = {}
    done = False
    for action in actions:
        _, _, done, info = env.step(action)
        if done:
            break
    return env, done, info


def test_variant_invariants() -> None:
    base_map = {scenario.id: scenario for scenario in load_base_scenarios()}
    suite = generate_scenario_suite(seed=55, num_variants_per_base=5)
    variants = [scenario for scenario in suite if scenario.variant_of is not None]

    assert len(variants) == 40

    for variant in variants:
        base = base_map[variant.variant_of]
        assert variant.ground_truth_root_cause_id == base.ground_truth_root_cause_id
        assert sorted(variant.allowed_mitigations) == sorted(base.allowed_mitigations)

        log_service = _key_log_service(variant)
        found_key_log = False
        for page in range(4):
            env = IncidentCommanderEnv(scenario=variant)
            env.reset(seed=123)
            env.step({"type": "wait", "args": {"steps": 2}})
            _, _, _, info = env.step(
                {
                    "type": "get_logs",
                    "args": {
                        "service": log_service,
                        "query": _key_log_query(variant),
                        "window_steps": 25,
                        "limit": 10,
                        "page": page,
                    },
                }
            )
            lines = info["tool_result"]["lines"]
            if any(
                any(term.casefold() in line["message"].casefold() for term in variant.evidence_markers["key_log_terms"])
                for line in lines
            ):
                found_key_log = True
                break
        assert found_key_log, variant.id

        env, done, info = _resolve_with_metadata(variant)
        assert done is True, variant.id
        assert info["resolution"] == "success", variant.id
        assert env.state is not None
        assert env.state.resolved_state is True, variant.id
        for requirement in variant.resolution_rubric.required_verification:
            assert (
                env.state.metrics[requirement.service][requirement.metric][-1] <= requirement.target
            ), variant.id
