"""Shared action schemas and constants for Stage 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

METRIC_NAMES: tuple[str, ...] = (
    "error_rate",
    "p95_latency",
    "cpu",
    "pricing_timeouts",
    "db_conn",
    "queue_depth",
    "memory_usage",
    "retry_rate",
    "dependency_503_rate",
    "access_denied_rate",
)

RUNBOOK_SECTIONS: tuple[str, ...] = ("triage", "mitigation", "verification")
AGGREGATIONS: tuple[str, ...] = ("raw", "mean", "p95")
SEVERITIES: tuple[str, ...] = ("sev1", "sev2", "sev3")
ROLE_NAMES: tuple[str, ...] = ("ic", "comms", "scribe", "ops")
TEAMS: tuple[str, ...] = ("db", "network", "pricing", "platform")
POST_UPDATE_AUDIENCES: tuple[str, ...] = ("internal", "external")
POST_UPDATE_TEMPLATES: tuple[str, ...] = ("initial", "status", "mitigation", "resolved")

POST_UPDATE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "initial": ("summary", "impact"),
    "status": ("summary", "eta"),
    "mitigation": ("mitigation", "owner"),
    "resolved": ("summary", "customer_impact"),
}

ACTION_TYPES: tuple[str, ...] = (
    "ack_alert",
    "list_services",
    "describe_service",
    "get_metrics",
    "get_logs",
    "get_trace_sample",
    "search_recent_deploys",
    "diff_config",
    "view_runbook",
    "create_incident",
    "assign_role",
    "post_update",
    "request_help",
    "apply_mitigation",
    "toggle_feature_flag",
    "apply_config_patch",
    "rollback_deploy",
    "restart_service",
    "scale_service",
    "run_health_check",
    "wait",
    "confirm_metrics_normalized",
    "declare_resolved",
    "declare_failed",
)


@dataclass(frozen=True)
class ArgumentSpec:
    """Describes one action argument."""

    type_name: str
    required: bool = True
    enum: tuple[str, ...] | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type_name,
            "required": self.required,
        }
        if self.enum is not None:
            payload["enum"] = list(self.enum)
        if self.min_value is not None:
            payload["min"] = self.min_value
        if self.max_value is not None:
            payload["max"] = self.max_value
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class ActionSpec:
    """Defines one allowed action."""

    action_type: str
    group: str
    args: dict[str, ArgumentSpec]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            "group": self.group,
            "arg_schema": {name: spec.to_dict() for name, spec in self.args.items()},
            "description": self.description,
        }


ACTION_SPECS: dict[str, ActionSpec] = {
    "ack_alert": ActionSpec(
        "ack_alert",
        "investigation",
        {"alert_id": ArgumentSpec("str", description="Identifier of an active alert.")},
        "Acknowledge an alert.",
    ),
    "list_services": ActionSpec(
        "list_services",
        "investigation",
        {},
        "List services involved in the incident.",
    ),
    "describe_service": ActionSpec(
        "describe_service",
        "investigation",
        {"service": ArgumentSpec("str", description="Service name.")},
        "Describe a service and its dependencies.",
    ),
    "get_metrics": ActionSpec(
        "get_metrics",
        "investigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "metric": ArgumentSpec("str", enum=METRIC_NAMES, description="Metric to inspect."),
            "window_steps": ArgumentSpec("int", min_value=1, max_value=25, description="Number of steps to inspect."),
            "agg": ArgumentSpec("str", enum=AGGREGATIONS, description="Aggregation mode."),
        },
        "Retrieve metric history for a service.",
    ),
    "get_logs": ActionSpec(
        "get_logs",
        "investigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "query": ArgumentSpec("str", description="Case-insensitive substring filter."),
            "window_steps": ArgumentSpec("int", min_value=1, max_value=25, description="Lookback window."),
            "limit": ArgumentSpec("int", min_value=1, max_value=50, description="Page size."),
            "page": ArgumentSpec("int", min_value=0, description="Zero-based page number."),
        },
        "Query paginated logs.",
    ),
    "get_trace_sample": ActionSpec(
        "get_trace_sample",
        "investigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "trace_id": ArgumentSpec("str", description="Trace identifier."),
        },
        "Retrieve a synthetic trace summary.",
    ),
    "search_recent_deploys": ActionSpec(
        "search_recent_deploys",
        "investigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "window_steps": ArgumentSpec("int", min_value=1, max_value=25, description="Lookback window."),
        },
        "Search recent deploy events.",
    ),
    "diff_config": ActionSpec(
        "diff_config",
        "investigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "from_version": ArgumentSpec("str", description="Source version."),
            "to_version": ArgumentSpec("str", description="Destination version."),
        },
        "Diff config between versions.",
    ),
    "view_runbook": ActionSpec(
        "view_runbook",
        "investigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "section": ArgumentSpec("str", enum=RUNBOOK_SECTIONS, description="Runbook section."),
        },
        "View a runbook section.",
    ),
    "create_incident": ActionSpec(
        "create_incident",
        "coordination",
        {
            "title": ArgumentSpec("str", description="Incident title."),
            "severity": ArgumentSpec("str", enum=SEVERITIES, description="Declared severity."),
        },
        "Create the incident record.",
    ),
    "assign_role": ActionSpec(
        "assign_role",
        "coordination",
        {
            "role": ArgumentSpec("str", enum=ROLE_NAMES, description="Role to assign."),
            "assignee": ArgumentSpec("str", description="Assignee name."),
        },
        "Assign an incident role.",
    ),
    "post_update": ActionSpec(
        "post_update",
        "coordination",
        {
            "audience": ArgumentSpec("str", enum=POST_UPDATE_AUDIENCES, description="Target audience."),
            "template_id": ArgumentSpec("str", enum=POST_UPDATE_TEMPLATES, description="Update template."),
            "fields": ArgumentSpec("dict", description="Structured template fields."),
        },
        "Post a structured update.",
    ),
    "request_help": ActionSpec(
        "request_help",
        "coordination",
        {
            "team": ArgumentSpec("str", enum=TEAMS, description="Team to contact."),
            "question": ArgumentSpec("str", description="Question for the team."),
        },
        "Request help from another team.",
    ),
    "apply_mitigation": ActionSpec(
        "apply_mitigation",
        "mitigation",
        {"mitigation_id": ArgumentSpec("str", description="Mitigation identifier.")},
        "Propose a mitigation plan; does not change system state directly.",
    ),
    "toggle_feature_flag": ActionSpec(
        "toggle_feature_flag",
        "mitigation",
        {
            "flag": ArgumentSpec("str", description="Feature flag name."),
            "enabled": ArgumentSpec("bool", description="Desired flag state."),
        },
        "Toggle a feature flag.",
    ),
    "apply_config_patch": ActionSpec(
        "apply_config_patch",
        "mitigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "patch_id": ArgumentSpec("str", description="Patch identifier."),
        },
        "Apply a config patch.",
    ),
    "rollback_deploy": ActionSpec(
        "rollback_deploy",
        "mitigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "from_version": ArgumentSpec("str", description="Current version."),
            "to_version": ArgumentSpec("str", description="Target version."),
        },
        "Rollback a deployment.",
    ),
    "restart_service": ActionSpec(
        "restart_service",
        "mitigation",
        {"service": ArgumentSpec("str", description="Service name.")},
        "Execute a service restart.",
    ),
    "scale_service": ActionSpec(
        "scale_service",
        "mitigation",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "replicas": ArgumentSpec("int", min_value=1, max_value=20, description="Desired replica count."),
        },
        "Scale a service to a new replica count.",
    ),
    "run_health_check": ActionSpec(
        "run_health_check",
        "verification",
        {"service": ArgumentSpec("str", description="Service name.")},
        "Run a synthetic health check.",
    ),
    "wait": ActionSpec(
        "wait",
        "verification",
        {"steps": ArgumentSpec("int", min_value=1, max_value=5, description="Steps to advance.")},
        "Advance time without taking other action.",
    ),
    "confirm_metrics_normalized": ActionSpec(
        "confirm_metrics_normalized",
        "verification",
        {
            "service": ArgumentSpec("str", description="Service name."),
            "metric": ArgumentSpec("str", enum=METRIC_NAMES, description="Metric to confirm."),
            "target": ArgumentSpec("float", min_value=0.0, description="Target threshold."),
            "window_steps": ArgumentSpec("int", min_value=1, max_value=10, description="Lookback window."),
        },
        "Confirm a metric meets a threshold.",
    ),
    "declare_resolved": ActionSpec(
        "declare_resolved",
        "termination",
        {
            "root_cause_id": ArgumentSpec("str", description="Diagnosed root cause identifier."),
            "mitigation_id": ArgumentSpec("str", description="Mitigation believed to have resolved the incident."),
            "summary": ArgumentSpec("str", description="Resolution summary."),
        },
        "Declare the incident resolved.",
    ),
    "declare_failed": ActionSpec(
        "declare_failed",
        "termination",
        {"reason": ArgumentSpec("str", description="Reason for failure.")},
        "End the episode as failed.",
    ),
}


def available_action_schemas() -> list[dict[str, Any]]:
    """Return CLI-friendly action schemas in a stable order."""

    return [ACTION_SPECS[action_type].to_dict() for action_type in ACTION_TYPES]
