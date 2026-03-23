"""CLI-friendly rendering helpers."""

from __future__ import annotations


def render_observation(obs: dict) -> str:
    """Render a concise textual view of an observation."""

    alert_lines = [
        f"- {alert['id']} | {alert['service']} | {alert['signal']} | active={alert['active']}"
        for alert in obs["alerts"]
    ]
    if not alert_lines:
        alert_lines = ["- none"]

    metric_snapshot = obs["metrics_snapshot"]
    metrics_line = ", ".join(
        f"{metric}={value:.2f}" for metric, value in sorted(metric_snapshot.items())
    )

    message_lines = [
        f"- step {message['ts_step']} | {message['from']}: {message['text']}"
        for message in obs["messages"][-3:]
    ]
    if not message_lines:
        message_lines = ["- none"]

    action_lines = [
        f"- {action['type']} {action['args']}"
        for action in obs["recent_actions"][-3:]
    ]
    if not action_lines:
        action_lines = ["- none"]

    evidence_flags = ", ".join(
        f"{key}={value}" for key, value in sorted(obs["evidence_flags"].items())
    )
    roles = ", ".join(f"{role}:{assignee}" for role, assignee in sorted(obs["incident"]["roles"].items()))
    roles = roles or "none"
    available_action_types = ", ".join(action["type"] for action in obs["available_actions"])

    sections = [
        f"Step: {obs['step']}",
        f"Status: {obs['status']}",
        f"Severity: {obs['severity']}",
        f"Incident created: {obs['incident']['created']}",
        f"Assigned roles: {roles}",
        "Alerts:",
        *alert_lines,
        f"Metrics: {metrics_line}",
        f"Evidence: {evidence_flags}",
        "Recent messages:",
        *message_lines,
        "Recent actions:",
        *action_lines,
        f"Available actions: {available_action_types}",
    ]
    return "\n".join(sections)
