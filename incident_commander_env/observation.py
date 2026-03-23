"""Observation builder."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .schemas import available_action_schemas
from .scenario import (
    scenario_category,
    scenario_log_service_hint,
    scenario_primary_service,
    scenario_query_hints,
    scenario_root_cause_candidates,
)


def _summarize_tool_result(tool_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if tool_result is None:
        return None
    if "metric" in tool_result and "series" in tool_result:
        return {
            "service": tool_result["service"],
            "metric": tool_result["metric"],
            "agg": tool_result["agg"],
        }
    if "lines" in tool_result:
        first_line = tool_result["lines"][0]["message"][:80] if tool_result["lines"] else None
        return {
            "service": tool_result["lines"][0]["service"] if tool_result["lines"] else None,
            "returned_lines": len(tool_result["lines"]),
            "next_page": tool_result["next_page"],
            "sample": first_line,
        }
    if "events" in tool_result:
        return {"events": len(tool_result["events"])}
    if "diff" in tool_result:
        return {"keys": [item["key"] for item in tool_result["diff"][:3]]}
    if "trace_id" in tool_result:
        return {
            "trace_id": tool_result["trace_id"],
            "error": tool_result["error"],
            "duration_ms": tool_result["duration_ms"],
        }
    if "healthy" in tool_result:
        return {"service": tool_result["service"], "healthy": tool_result["healthy"]}
    if "team" in tool_result:
        return {"team": tool_result["team"], "response": tool_result["response"][:80]}
    if "content" in tool_result:
        return {
            "service": tool_result["service"],
            "section": tool_result["section"],
            "items": len(tool_result["content"]),
        }
    return deepcopy(tool_result)


def build_observation(env_state: Any, scenario: Any) -> dict[str, Any]:
    """Build a structured observation from environment state."""

    step = env_state.current_step
    primary_service = scenario_primary_service(scenario)
    log_service_hint = scenario_log_service_hint(scenario)
    category = scenario_category(scenario)
    metrics_snapshot: dict[str, float] = {}
    for service_metrics in env_state.metrics.values():
        for metric_name, series in service_metrics.items():
            metrics_snapshot.setdefault(metric_name, float(series[-1]))
    alerts = [
        {
            "id": alert.id,
            "service": alert.service,
            "signal": alert.signal,
            "active": alert.active,
            "acknowledged": alert.acknowledged,
        }
        for alert in env_state.active_alerts
    ]
    alerts.sort(key=lambda item: item["id"])

    messages = [
        {"ts_step": message.ts_step, "from": message.sender, "text": message.text}
        for message in env_state.message_feed
    ]
    recent_actions = deepcopy(env_state.applied_actions[-5:])
    last_tool_results = {
        key: _summarize_tool_result(value)
        for key, value in env_state.last_tool_results.items()
        if value is not None
    }
    action_catalog = {
        "primary_service": primary_service,
        "log_service": log_service_hint,
        "services": sorted(scenario.evidence.services.keys()),
        "query_hints": scenario_query_hints(scenario),
        "rollback_options": sorted(
            [
                {
                    "service": event.service,
                    "from_version": event.to_version,
                    "to_version": event.from_version,
                }
                for event in scenario.evidence.deploy_history
            ],
            key=lambda item: (item["service"], item["from_version"], item["to_version"]),
        ),
        "config_diff_options": sorted(
            [
                {
                    "service": record.service,
                    "from_version": record.from_version,
                    "to_version": record.to_version,
                }
                for record in scenario.evidence.config_diffs
            ],
            key=lambda item: (item["service"], item["from_version"], item["to_version"]),
        ),
        "config_patches": sorted(
            [
                {"service": service, "patch_id": patch_id}
                for service, patch_ids in scenario.patch_ids.items()
                for patch_id in patch_ids
            ],
            key=lambda item: (item["service"], item["patch_id"]),
        ),
        "feature_flags": sorted(
            [
                {"flag": flag, "current_enabled": enabled}
                for flag, enabled in env_state.feature_flags.items()
            ],
            key=lambda item: item["flag"],
        ),
        "trace_samples": sorted(
            [
                {"service": sample.service, "trace_id": sample.trace_id}
                for sample in scenario.evidence.trace_samples
            ],
            key=lambda item: (item["service"], item["trace_id"]),
        ),
        "runbook_services": sorted(scenario.evidence.runbook_snippets.keys()),
        "mitigation_actions": sorted(
            [
                {
                    "mitigation_id": rule.mitigation_id,
                    "action_type": rule.action_type,
                    "args": deepcopy(rule.args_match),
                    "forbidden": rule.forbidden,
                }
                for rule in scenario.mitigation_rules
            ],
            key=lambda item: (item["mitigation_id"], item["action_type"], str(item["args"])),
        ),
    }
    resolution_hints = {
        "root_cause_candidates": scenario_root_cause_candidates(scenario),
        "verification_targets": [
            {
                "service": requirement.service,
                "metric": requirement.metric,
                "target": requirement.target,
                "window_steps": requirement.window_steps,
            }
            for requirement in scenario.resolution_rubric.required_verification
        ],
        "required_updates": [
            {
                "template_id": requirement.template_id,
                "audience": requirement.audience,
            }
            for requirement in scenario.resolution_rubric.required_updates
        ],
    }

    return {
        "step": step,
        "severity": scenario.severity,
        "status": env_state.incident_status,
        "alerts": alerts,
        "metrics_snapshot": metrics_snapshot,
        "messages": messages,
        "recent_actions": recent_actions,
        "available_actions": available_action_schemas(),
        "allowed_mitigations": list(scenario.allowed_mitigations),
        "notes": {"hint": "Use multiple tools before mitigation and verify stability before resolution."},
        "incident": {
            "created": env_state.incident_created,
            "severity": env_state.incident_severity,
            "roles": deepcopy(env_state.roles_assigned),
            "category": category,
            "primary_service": primary_service,
        },
        "evidence_flags": deepcopy(env_state.evidence_flags),
        "last_tool_results": last_tool_results,
        "action_catalog": action_catalog,
        "resolution_hints": resolution_hints,
    }
