"""Shared schemas for actions and environment-facing structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

METRIC_NAMES: tuple[str, ...] = (
    "error_rate",
    "p95_latency",
    "cpu",
    "pricing_timeouts",
)

POST_UPDATE_AUDIENCES: tuple[str, ...] = ("internal", "external")

ACTION_TYPES: tuple[str, ...] = (
    "ack_alert",
    "get_metrics",
    "get_logs",
    "view_runbook",
    "apply_mitigation",
    "post_update",
    "declare_resolved",
)


@dataclass(frozen=True)
class ArgumentSpec:
    """Describes one action argument for validation and observation hints."""

    type_name: str
    required: bool = True
    enum: tuple[str, ...] | None = None
    min_value: int | None = None
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
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class ActionSpec:
    """Defines one allowed action."""

    action_type: str
    args: dict[str, ArgumentSpec]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            "arg_schema": {name: spec.to_dict() for name, spec in self.args.items()},
            "description": self.description,
        }


ACTION_SPECS: dict[str, ActionSpec] = {
    "ack_alert": ActionSpec(
        action_type="ack_alert",
        args={
            "alert_id": ArgumentSpec(
                type_name="str",
                description="Identifier of an active alert.",
            )
        },
        description="Acknowledge an alert without resolving the incident.",
    ),
    "get_metrics": ActionSpec(
        action_type="get_metrics",
        args={
            "metric": ArgumentSpec(
                type_name="str",
                enum=METRIC_NAMES,
                description="Metric name to inspect.",
            ),
            "window": ArgumentSpec(
                type_name="int",
                min_value=1,
                description="Number of steps to retrieve, ending at the current step.",
            ),
        },
        description="Retrieve recent metric history.",
    ),
    "get_logs": ActionSpec(
        action_type="get_logs",
        args={
            "service": ArgumentSpec(
                type_name="str",
                description="Service name to query.",
            ),
            "query": ArgumentSpec(
                type_name="str",
                description="Case-insensitive substring filter.",
            ),
            "limit": ArgumentSpec(
                type_name="int",
                min_value=1,
                description="Page size for returned log lines.",
            ),
            "page": ArgumentSpec(
                type_name="int",
                min_value=1,
                description="One-based page number.",
            ),
        },
        description="Query scenario logs deterministically.",
    ),
    "view_runbook": ActionSpec(
        action_type="view_runbook",
        args={
            "service": ArgumentSpec(
                type_name="str",
                description="Service or component name.",
            )
        },
        description="Read a runbook snippet for a service.",
    ),
    "apply_mitigation": ActionSpec(
        action_type="apply_mitigation",
        args={
            "mitigation_id": ArgumentSpec(
                type_name="str",
                description="Mitigation identifier known to the scenario.",
            )
        },
        description="Apply a mitigation that may help resolve the incident.",
    ),
    "post_update": ActionSpec(
        action_type="post_update",
        args={
            "audience": ArgumentSpec(
                type_name="str",
                enum=POST_UPDATE_AUDIENCES,
                description="Audience for the update.",
            ),
            "template_id": ArgumentSpec(
                type_name="str",
                description="Template identifier for the message content.",
            ),
        },
        description="Post a communication update.",
    ),
    "declare_resolved": ActionSpec(
        action_type="declare_resolved",
        args={
            "root_cause_id": ArgumentSpec(
                type_name="str",
                description="Diagnosed root cause identifier.",
            ),
            "mitigation_id": ArgumentSpec(
                type_name="str",
                description="Mitigation believed to have resolved the incident.",
            ),
        },
        description="Declare the incident resolved and end the episode.",
    ),
}


def available_action_schemas() -> list[dict[str, Any]]:
    """Return CLI-friendly action schemas in a stable order."""

    return [ACTION_SPECS[action_type].to_dict() for action_type in ACTION_TYPES]
