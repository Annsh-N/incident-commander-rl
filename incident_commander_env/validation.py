"""Action validation logic."""

from __future__ import annotations

from typing import Any

from .schemas import ACTION_SPECS


def _is_str(value: Any) -> bool:
    return isinstance(value, str)


def _is_int(value: Any) -> bool:
    return type(value) is int


def validate_action(action: dict[str, Any], env_state: Any) -> tuple[bool, str | None]:
    """Validate an action against the strict Stage 1 schema."""

    if not isinstance(action, dict):
        return False, "action must be a dict"
    if set(action.keys()) != {"type", "args"}:
        return False, "action must contain exactly 'type' and 'args'"

    action_type = action.get("type")
    args = action.get("args")

    if not _is_str(action_type):
        return False, "action type must be a string"
    if action_type not in ACTION_SPECS:
        return False, f"unknown action type: {action_type}"
    if not isinstance(args, dict):
        return False, "action args must be a dict"

    spec = ACTION_SPECS[action_type]
    expected_keys = set(spec.args.keys())
    provided_keys = set(args.keys())
    if provided_keys != expected_keys:
        missing = sorted(expected_keys - provided_keys)
        extra = sorted(provided_keys - expected_keys)
        details: list[str] = []
        if missing:
            details.append(f"missing args: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected args: {', '.join(extra)}")
        return False, "; ".join(details)

    for arg_name, arg_spec in spec.args.items():
        value = args[arg_name]
        if arg_spec.type_name == "str" and not _is_str(value):
            return False, f"arg '{arg_name}' must be a string"
        if arg_spec.type_name == "int" and not _is_int(value):
            return False, f"arg '{arg_name}' must be an int"
        if arg_spec.enum is not None and value not in arg_spec.enum:
            return False, f"arg '{arg_name}' must be one of {list(arg_spec.enum)}"
        if arg_spec.min_value is not None and _is_int(value) and value < arg_spec.min_value:
            return False, f"arg '{arg_name}' must be >= {arg_spec.min_value}"

    scenario = env_state.scenario

    if action_type == "ack_alert":
        alert_ids = {alert.id for alert in env_state.active_alerts if alert.active}
        if args["alert_id"] not in alert_ids:
            return False, f"unknown active alert_id: {args['alert_id']}"
    elif action_type == "get_metrics":
        if args["metric"] not in scenario.evidence.metrics_by_step:
            return False, f"invalid metric name: {args['metric']}"
    elif action_type == "get_logs":
        if args["service"] not in scenario.evidence.logs_by_service:
            return False, f"unknown service for logs: {args['service']}"
    elif action_type == "view_runbook":
        if args["service"] not in scenario.runbook_snippets:
            return False, f"unknown service for runbook: {args['service']}"
    elif action_type in {"apply_mitigation", "declare_resolved"}:
        allowed_ids = set(scenario.allowed_mitigations) | set(scenario.forbidden_mitigations)
        if args["mitigation_id"] not in allowed_ids:
            return False, f"invalid mitigation_id: {args['mitigation_id']}"

    return True, None
