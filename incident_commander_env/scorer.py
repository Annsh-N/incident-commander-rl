"""Dense deterministic scoring for Stage 2."""

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

CORE_TOOL_ORDER = ("metrics", "logs", "deploy_config")


def _action_signature(action: dict[str, Any]) -> str:
    return json.dumps(action, sort_keys=True, separators=(",", ":"))


def _mark_core_tool_usage(state: Any, action_type: str) -> float:
    tool_class = None
    if action_type == "get_metrics":
        tool_class = "metrics"
    elif action_type == "get_logs":
        tool_class = "logs"
    elif action_type in {"search_recent_deploys", "diff_config"}:
        tool_class = "deploy_config"

    if tool_class is None or state.core_tool_rewarded[tool_class]:
        return 0.0

    if tool_class == "metrics":
        state.core_tool_rewarded[tool_class] = True
        return 0.05
    if tool_class == "logs" and state.core_tool_rewarded["metrics"]:
        state.core_tool_rewarded[tool_class] = True
        return 0.05
    if tool_class == "deploy_config" and state.core_tool_rewarded["logs"]:
        state.core_tool_rewarded[tool_class] = True
        return 0.05
    return 0.0


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
        if state.current_step <= 2:
            reward += 0.05
            state.rewards_claimed["incident_created_early"] = True
    elif action_type == "post_update":
        template_id = args["template_id"]
        if (
            template_id == "initial"
            and args["audience"] == "internal"
            and state.current_step <= 4
            and not state.rewards_claimed["initial_internal_update"]
        ):
            reward += 0.03
            state.rewards_claimed["initial_internal_update"] = True
        elif (
            template_id == "status"
            and state.mitigations_applied
            and not state.rewards_claimed["status_update_after_mitigation"]
        ):
            reward += 0.03
            state.rewards_claimed["status_update_after_mitigation"] = True
    elif action_type == "apply_mitigation":
        if args["mitigation_id"] in scenario.forbidden_mitigations:
            reward -= 0.2
            state.unsafe_attempt = True
            info_updates["unsafe_attempt"] = True
            info_updates["debug"].append("Forbidden mitigation proposed.")
    elif action_type in {"restart_service", "scale_service"}:
        executed_mitigation = state.last_executed_mitigation_id
        if executed_mitigation in scenario.forbidden_mitigations:
            reward -= 0.2
            state.unsafe_attempt = True
            info_updates["unsafe_attempt"] = True
            info_updates["debug"].append("Forbidden concrete service change attempted.")
    elif action_type == "declare_resolved":
        if not state.incident_created or not state.updates_posted:
            reward -= 0.1
            info_updates["debug"].append(
                "Resolution declaration lacked incident creation or communication updates."
            )
        failure_reasons: list[str] = []
        if not state.incident_created:
            failure_reasons.append("no_incident_created")
        if not state.updates_posted:
            failure_reasons.append("no_comms_update")
        if not state.proposed_mitigations:
            failure_reasons.append("no_proposed_mitigation")
        if state.causal_fix_step is None:
            failure_reasons.append("no_concrete_change")
        else:
            if not state.causal_change_planned:
                failure_reasons.append("change_not_preplanned")
            if not state.causal_change_evidence_met:
                failure_reasons.append("no_evidence_before_change")
            if state.current_step <= state.causal_fix_step:
                failure_reasons.append("no_wait_after_change")
        if not state.confirmations["error_rate"]:
            failure_reasons.append("error_rate_not_confirmed")
        if not state.confirmations["p95_latency"]:
            failure_reasons.append("p95_latency_not_confirmed")

        root_cause_matches = args["root_cause_id"] == scenario.ground_truth_root_cause_id
        mitigation_matches = args["mitigation_id"] == state.causal_mitigation_id
        if state.resolved_state and root_cause_matches and mitigation_matches:
            reward += 2.0
            done = True
            info_updates["resolution"] = "success"
        else:
            reward -= 1.0
            done = True
            if not state.resolved_state:
                info_updates["resolution"] = "unstable"
                info_updates["debug"].append(
                    "Resolution declared before the environment reached stable resolved state."
                )
                info_updates["failure_reasons"] = failure_reasons
            elif not root_cause_matches:
                info_updates["resolution"] = "wrong_root_cause"
                info_updates["debug"].append("Incorrect root cause in resolution declaration.")
                info_updates["failure_reasons"] = ["wrong_root_cause"]
            else:
                info_updates["resolution"] = "wrong_mitigation"
                info_updates["debug"].append("Incorrect mitigation in resolution declaration.")
                info_updates["failure_reasons"] = ["wrong_mitigation"]
    elif action_type == "declare_failed":
        done = True
        info_updates["resolution"] = "failed"

    if tool_result is not None:
        if action_type == "get_logs":
            if not state.evidence_flags["saw_key_log"]:
                saw_key_log = any(
                    "PRICING_URL invalid" in line["message"] for line in tool_result.get("lines", [])
                )
                if saw_key_log:
                    state.evidence_flags["saw_key_log"] = True
                    reward += 0.05
        elif action_type == "search_recent_deploys":
            if not state.evidence_flags["saw_deploy"]:
                if any(event["to_version"] == "v42" for event in tool_result.get("events", [])):
                    state.evidence_flags["saw_deploy"] = True
                    reward += 0.05
        elif action_type == "diff_config":
            if not state.evidence_flags["saw_config_diff"]:
                if any(entry["key"] == "PRICING_URL" for entry in tool_result.get("diff", [])):
                    state.evidence_flags["saw_config_diff"] = True
                    reward += 0.05
        elif action_type == "get_trace_sample":
            if not state.evidence_flags["saw_timeout_trace"]:
                if tool_result.get("error") and "timeout" in tool_result["error"]:
                    state.evidence_flags["saw_timeout_trace"] = True
                    reward += 0.05

    reward = round(reward, 10)
    return reward, done, info_updates
