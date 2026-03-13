"""Action validation logic for Stage 2."""

from __future__ import annotations

from typing import Any

from .schemas import ACTION_SPECS, POST_UPDATE_REQUIRED_FIELDS


def _is_str(value: Any) -> bool:
    return isinstance(value, str)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_bool(value: Any) -> bool:
    return type(value) is bool


def _is_float_like(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_action(action: dict[str, Any], env_state: Any) -> tuple[bool, str | None]:
    """Validate an action against the strict Stage 2 schema."""

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
        if arg_spec.type_name == "bool" and not _is_bool(value):
            return False, f"arg '{arg_name}' must be a bool"
        if arg_spec.type_name == "dict" and not isinstance(value, dict):
            return False, f"arg '{arg_name}' must be a dict"
        if arg_spec.type_name == "float" and not _is_float_like(value):
            return False, f"arg '{arg_name}' must be a float"
        if arg_spec.enum is not None and value not in arg_spec.enum:
            return False, f"arg '{arg_name}' must be one of {list(arg_spec.enum)}"
        if arg_spec.min_value is not None and _is_float_like(value) and value < arg_spec.min_value:
            return False, f"arg '{arg_name}' must be >= {arg_spec.min_value}"
        if arg_spec.max_value is not None and _is_float_like(value) and value > arg_spec.max_value:
            return False, f"arg '{arg_name}' must be <= {arg_spec.max_value}"

    scenario = env_state.scenario
    known_services = set(scenario.evidence.services.keys())
    known_metrics = {
        service: set(metric_map.keys()) for service, metric_map in env_state.metrics.items()
    }

    if action_type == "ack_alert":
        alert_ids = {alert.id for alert in env_state.active_alerts if alert.active}
        if args["alert_id"] not in alert_ids:
            return False, f"unknown active alert_id: {args['alert_id']}"
    elif action_type in {
        "describe_service",
        "get_metrics",
        "get_logs",
        "get_trace_sample",
        "search_recent_deploys",
        "diff_config",
        "view_runbook",
        "apply_config_patch",
        "rollback_deploy",
        "run_health_check",
        "confirm_metrics_normalized",
    }:
        service = args["service"]
        if service not in known_services:
            return False, f"unknown service: {service}"

    if action_type == "get_metrics":
        if args["metric"] not in known_metrics[args["service"]]:
            return False, f"metric '{args['metric']}' is not available for {args['service']}"
    elif action_type == "get_logs":
        if args["service"] not in scenario.evidence.logs_by_service:
            return False, f"unknown service for logs: {args['service']}"
    elif action_type == "get_trace_sample":
        trace_id = args["trace_id"]
        if trace_id not in scenario.evidence.trace_samples:
            return False, f"unknown trace_id: {trace_id}"
        if scenario.evidence.trace_samples[trace_id].service != args["service"]:
            return False, f"trace_id {trace_id} does not belong to {args['service']}"
    elif action_type == "diff_config":
        service_diffs = scenario.evidence.config_diffs.get(args["service"], {})
        version_pair = (args["from_version"], args["to_version"])
        if version_pair not in service_diffs:
            return False, f"unknown config diff for {args['service']} {version_pair}"
    elif action_type == "view_runbook":
        if args["service"] not in scenario.evidence.runbook_snippets:
            return False, f"no runbook for service: {args['service']}"
    elif action_type == "post_update":
        required_fields = POST_UPDATE_REQUIRED_FIELDS[args["template_id"]]
        field_keys = set(args["fields"].keys())
        missing_fields = [key for key in required_fields if key not in field_keys]
        if missing_fields:
            return False, f"missing fields for template {args['template_id']}: {missing_fields}"
        for key, value in args["fields"].items():
            if not _is_str(key) or not _is_str(value):
                return False, "post_update fields must map strings to strings"
    elif action_type == "apply_mitigation":
        if args["mitigation_id"] not in scenario.all_mitigations:
            return False, f"invalid mitigation_id: {args['mitigation_id']}"
    elif action_type == "toggle_feature_flag":
        if args["flag"] not in env_state.feature_flags:
            return False, f"unknown feature flag: {args['flag']}"
    elif action_type == "apply_config_patch":
        if args["patch_id"] not in scenario.patch_ids.get(args["service"], ()):
            return False, f"unknown patch_id {args['patch_id']} for {args['service']}"
    elif action_type == "rollback_deploy":
        current_version = env_state.deploy_versions[args["service"]]
        if args["from_version"] != current_version:
            return False, f"from_version must match current version {current_version}"
    elif action_type == "confirm_metrics_normalized":
        if args["metric"] not in known_metrics[args["service"]]:
            return False, f"metric '{args['metric']}' is not available for {args['service']}"
    elif action_type == "declare_resolved":
        if args["mitigation_id"] not in scenario.all_mitigations:
            return False, f"invalid mitigation_id: {args['mitigation_id']}"
        if not args["summary"].strip():
            return False, "summary must be non-empty"
    elif action_type == "declare_failed":
        if not args["reason"].strip():
            return False, "reason must be non-empty"

    return True, None
