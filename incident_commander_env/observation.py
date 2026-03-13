"""Observation builder."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .schemas import available_action_schemas


def build_observation(env_state: Any, scenario: Any) -> dict[str, Any]:
    """Build a structured observation from environment state."""

    step = env_state.current_step
    metrics_snapshot = {
        metric: float(values[min(step, len(values) - 1)])
        for metric, values in env_state.metrics.items()
    }
    alerts = [
        {
            "id": alert.id,
            "service": alert.service,
            "signal": alert.signal,
            "active": alert.active,
        }
        for alert in env_state.active_alerts
    ]
    alerts.sort(key=lambda item: item["id"])

    messages = [
        {"ts_step": message.ts_step, "from": message.sender, "text": message.text}
        for message in env_state.message_feed
    ]
    recent_actions = deepcopy(env_state.applied_actions[-5:])

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
        "notes": {"hint": "Use tools to gather evidence before declaring resolution."},
    }
