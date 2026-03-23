from incident_commander_env import IncidentCommanderEnv, generate_scenario_suite
from incident_commander_env.scenario import load_base_scenarios


def _resolve_with_metadata(scenario) -> tuple[bool, dict]:
    env = IncidentCommanderEnv(scenario=scenario)
    env.reset(seed=999)

    first_service = next(iter(scenario.evidence.services.keys()))
    first_metric = next(iter(scenario.evidence.metric_profiles[first_service].keys()))
    first_diff = scenario.evidence.config_diffs[0]
    key_log_service = first_service
    for service, entries in scenario.evidence.logs_by_service.items():
        if any(
            any(term in entry.message for term in scenario.evidence_markers["key_log_terms"])
            for entry in entries
        ):
            key_log_service = service
            break
    actions = [
        {"type": "create_incident", "args": {"title": scenario.title, "severity": scenario.severity}},
        {"type": "get_metrics", "args": {"service": first_service, "metric": first_metric, "window_steps": 1, "agg": "raw"}},
        {"type": "get_logs", "args": {"service": key_log_service, "query": scenario.evidence_markers["key_log_terms"][0].split()[0], "window_steps": 6, "limit": 10, "page": 0}},
        {"type": "search_recent_deploys", "args": {"service": scenario.evidence_markers["deploy_service"], "window_steps": 6}},
        {"type": "diff_config", "args": {"service": first_diff.service, "from_version": first_diff.from_version, "to_version": first_diff.to_version}},
    ]
    if "saw_timeout_trace" in scenario.resolution_rubric.required_evidence_flags:
        trace_id = next(
            sample.trace_id
            for sample in scenario.evidence.trace_samples
            if sample.error
            and any(
                term.casefold() in sample.error.casefold()
                for term in scenario.evidence_markers.get("trace_error_terms", [])
            )
        )
        trace_service = next(
            sample.service
            for sample in scenario.evidence.trace_samples
            if sample.trace_id == trace_id
        )
        actions.append(
            {
                "type": "get_trace_sample",
                "args": {"service": trace_service, "trace_id": trace_id},
            }
        )
    if "saw_runbook" in scenario.resolution_rubric.required_evidence_flags:
        runbook_service = next(iter(scenario.evidence.runbook_snippets.keys()))
        actions.append({"type": "view_runbook", "args": {"service": runbook_service, "section": "triage"}})
    actions.append({"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Mitigation in progress", "eta": "10 minutes"}}})
    actions.append({"type": "apply_mitigation", "args": {"mitigation_id": scenario.allowed_mitigations[0]}})
    for rule in scenario.mitigation_rules:
        if rule.causal and rule.mitigation_id == scenario.allowed_mitigations[0]:
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
                "mitigation_id": scenario.allowed_mitigations[0],
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
    return done, info


def test_variant_invariants() -> None:
    base_map = {scenario.id: scenario for scenario in load_base_scenarios()}
    suite = generate_scenario_suite(seed=55, num_variants_per_base=1)
    variants = [scenario for scenario in suite if scenario.variant_of is not None]

    for variant in variants[:4]:
        base = base_map[variant.variant_of]
        assert variant.ground_truth_root_cause_id == base.ground_truth_root_cause_id
        assert sorted(variant.allowed_mitigations) == sorted(base.allowed_mitigations)
        done, info = _resolve_with_metadata(variant)
        assert done is True
        assert info["resolution"] == "success"
