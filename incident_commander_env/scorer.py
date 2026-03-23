"""Dense deterministic scoring for Stage 3."""

from __future__ import annotations

import json
from typing import Any


SPAM_TRACKED_ACTIONS = {
    "get_metrics",
    "get_logs",
    "search_recent_deploys",
    "diff_config",
    "get_trace_sample",
    "view_runbook",
}

INVESTIGATION_CATEGORY_MAP = {
    "get_metrics": "metrics",
    "get_logs": "logs",
    "search_recent_deploys": "deploys",
    "diff_config": "config",
    "get_trace_sample": "traces",
    "view_runbook": "runbook",
}


def _action_signature(action: dict[str, Any]) -> str:
    return json.dumps(action, sort_keys=True, separators=(",", ":"))


def _mark_core_tool_usage(state: Any, action_type: str) -> float:
    category = INVESTIGATION_CATEGORY_MAP.get(action_type)
    if category is None:
        return 0.0
    state.investigation_categories_used.add(category)
    if category in state.tool_rewarded:
        return 0.0
    state.tool_rewarded.add(category)
    return 0.05


def _required_updates_satisfied(state: Any, scenario: Any) -> list[str]:
    posted = {
        (update["template_id"], update["audience"])
        for update in state.updates_posted
    }
    missing = []
    for requirement in scenario.resolution_rubric.required_updates:
        key = (requirement.template_id, requirement.audience)
        if key not in posted:
            missing.append(f"{requirement.audience}:{requirement.template_id}")
    return missing


def _verification_missing(state: Any, scenario: Any) -> list[str]:
    missing = []
    for requirement in scenario.resolution_rubric.required_verification:
        key = (requirement.service, requirement.metric)
        if not state.verification_results.get(key, False):
            missing.append(f"{requirement.service}:{requirement.metric}")
    return missing


def _required_evidence_missing(state: Any, scenario: Any) -> list[str]:
    return [
        flag
        for flag in scenario.resolution_rubric.required_evidence_flags
        if not state.evidence_flags.get(flag, False)
    ]


def _update_evidence_flags(state: Any, action_type: str, tool_result: dict[str, Any], scenario: Any) -> float:
    reward = 0.0
    markers = scenario.evidence_markers

    if action_type == "get_logs" and not state.evidence_flags["saw_key_log"]:
        saw_key_log = any(
            any(term.casefold() in line["message"].casefold() for term in markers.get("key_log_terms", []))
            for line in tool_result.get("lines", [])
        )
        if saw_key_log:
            state.evidence_flags["saw_key_log"] = True
            reward += 0.05
    elif action_type == "search_recent_deploys" and not state.evidence_flags["saw_deploy"]:
        saw_deploy = any(
            event["service"] == markers.get("deploy_service")
            and event["to_version"] == markers.get("deploy_to_version")
            for event in tool_result.get("events", [])
        )
        if saw_deploy:
            state.evidence_flags["saw_deploy"] = True
            reward += 0.05
    elif action_type == "diff_config" and not state.evidence_flags["saw_config_diff"]:
        saw_diff = any(
            entry["key"] in markers.get("config_keys", [])
            for entry in tool_result.get("diff", [])
        )
        if saw_diff:
            state.evidence_flags["saw_config_diff"] = True
            reward += 0.05
    elif action_type == "get_trace_sample" and not state.evidence_flags["saw_timeout_trace"]:
        error_text = tool_result.get("error") or ""
        if any(term.casefold() in error_text.casefold() for term in markers.get("trace_error_terms", [])):
            state.evidence_flags["saw_timeout_trace"] = True
            reward += 0.05
    elif action_type == "view_runbook" and not state.evidence_flags["saw_runbook"]:
        state.evidence_flags["saw_runbook"] = True
        reward += 0.02

    return reward


def score_step(
    state: Any,
    action: dict[str, Any],
    tool_result: dict[str, Any] | None,
    scenario: Any,
) -> tuple[float, bool, dict[str, Any]]:
    """Return deterministic dense reward and termination metadata."""

    reward = -0.02
    done = False
    action_type = action["type"]
    args = action["args"]
    info_updates: dict[str, Any] = {
        "resolution": None,
        "debug": [],
        "unsafe_attempt": state.unsafe_attempt,
        "failure_reasons": [],
    }

    signature = _action_signature(action)
    state.action_signature_counts[signature] = state.action_signature_counts.get(signature, 0) + 1
    if action_type in SPAM_TRACKED_ACTIONS and state.action_signature_counts[signature] > 3:
        reward -= 0.1
        info_updates["debug"].append("Repeated identical tool action triggered spam penalty.")

    reward += _mark_core_tool_usage(state, action_type)

    if action_type == "create_incident" and not state.rewards_claimed["incident_created_early"]:
        if state.current_step <= scenario.resolution_rubric.create_incident_by:
            reward += 0.05
            state.rewards_claimed["incident_created_early"] = True
    elif action_type == "post_update":
        key = (args["template_id"], args["audience"])
        if key not in state.rewarded_updates:
            reward += 0.03
            state.rewarded_updates.add(key)
    elif action_type == "apply_mitigation":
        if args["mitigation_id"] in scenario.forbidden_mitigations:
            reward -= 0.2
            state.unsafe_attempt = True
            info_updates["unsafe_attempt"] = True
            info_updates["debug"].append("Forbidden mitigation proposed.")
    elif action_type in {"restart_service", "scale_service", "rollback_deploy", "apply_config_patch", "toggle_feature_flag"}:
        executed_mitigation = state.last_executed_mitigation_id
        if executed_mitigation in scenario.forbidden_mitigations:
            reward -= 0.2
            state.unsafe_attempt = True
            info_updates["unsafe_attempt"] = True
            info_updates["debug"].append("Forbidden concrete service change attempted.")
    elif action_type == "declare_resolved":
        failure_reasons: list[str] = []
        if not state.incident_created:
            failure_reasons.append("no_incident_created")
        missing_updates = _required_updates_satisfied(state, scenario)
        if missing_updates:
            failure_reasons.extend(f"missing_update:{item}" for item in missing_updates)
        if len(state.investigation_categories_used) < scenario.resolution_rubric.min_investigation_categories:
            failure_reasons.append("insufficient_investigation")
        missing_evidence = _required_evidence_missing(state, scenario)
        if missing_evidence:
            failure_reasons.extend(f"missing_evidence:{flag}" for flag in missing_evidence)
        if state.causal_fix_step is None:
            failure_reasons.append("no_concrete_change")
        else:
            if not state.causal_change_planned:
                failure_reasons.append("change_not_preplanned")
            if not state.causal_change_evidence_met:
                failure_reasons.append("no_evidence_before_change")
            if state.current_step <= state.causal_fix_step:
                failure_reasons.append("no_wait_after_change")
        missing_verifications = _verification_missing(state, scenario)
        if missing_verifications:
            failure_reasons.extend(f"missing_verification:{item}" for item in missing_verifications)

        root_cause_matches = args["root_cause_id"] == scenario.ground_truth_root_cause_id
        mitigation_matches = args["mitigation_id"] == state.causal_mitigation_id
        if state.resolved_state and root_cause_matches and mitigation_matches and not failure_reasons:
            reward += 2.0
            done = True
            info_updates["resolution"] = "success"
        else:
            reward -= 1.0
            done = True
            if not root_cause_matches:
                info_updates["resolution"] = "wrong_root_cause"
                info_updates["failure_reasons"] = ["wrong_root_cause", *failure_reasons]
            elif not mitigation_matches:
                info_updates["resolution"] = "wrong_mitigation"
                info_updates["failure_reasons"] = ["wrong_mitigation", *failure_reasons]
            else:
                info_updates["resolution"] = "unstable"
                info_updates["failure_reasons"] = failure_reasons
            info_updates["debug"].append("Resolution declaration failed scenario rubric checks.")
    elif action_type == "declare_failed":
        done = True
        info_updates["resolution"] = "failed"

    if tool_result is not None:
        reward += _update_evidence_flags(state, action_type, tool_result, scenario)

    reward = round(reward, 10)
    return reward, done, info_updates
