"""Deterministic tool simulators for Stage 3."""

from __future__ import annotations

from statistics import mean
from typing import Any

from .scenario import Scenario


def _last_n(values: list[float], count: int) -> list[float]:
    return values[-count:] if count <= len(values) else list(values)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int(round(0.95 * (len(ordered) - 1))))
    return float(ordered[index])


def tool_list_services(scenario: Scenario) -> dict[str, Any]:
    """List services in the scenario."""

    services = [
        {
            "name": service.name,
            "owner": service.owner,
            "dependencies": list(service.dependencies),
        }
        for service in scenario.evidence.services.values()
    ]
    services.sort(key=lambda item: item["name"])
    return {"services": services}


def tool_describe_service(service: str, env_state: Any, scenario: Scenario) -> dict[str, Any]:
    """Describe one service."""

    definition = scenario.evidence.services[service]
    return {
        "service": definition.name,
        "description": definition.description,
        "dependencies": list(definition.dependencies),
        "owner": definition.owner,
        "current_version": env_state.deploy_versions[service],
        "runbook_sections": sorted(scenario.evidence.runbook_snippets.get(service, {}).keys()),
    }


def tool_get_metrics(
    service: str,
    metric: str,
    window_steps: int,
    agg: str,
    env_state: Any,
) -> dict[str, Any]:
    """Return metric history and an aggregate."""

    series = _last_n(env_state.metrics[service][metric], window_steps)
    if agg == "raw":
        agg_value = float(series[-1])
    elif agg == "mean":
        agg_value = round(float(mean(series)), 4)
    else:
        agg_value = round(_p95(series), 4)
    return {
        "service": service,
        "metric": metric,
        "series": [float(value) for value in series],
        "agg": agg_value,
        "aggregation": agg,
    }


def tool_get_logs(
    service: str,
    query: str,
    window_steps: int,
    limit: int,
    page: int,
    current_step: int,
    scenario: Scenario,
) -> dict[str, Any]:
    """Return paginated logs filtered by window and query."""

    start_step = max(0, current_step - window_steps + 1)
    entries = [
        entry
        for entry in scenario.evidence.logs_by_service.get(service, ())
        if start_step <= entry.step <= current_step
    ]
    query_text = query.casefold()
    if query_text:
        entries = [entry for entry in entries if query_text in entry.message.casefold()]

    start_index = page * limit
    end_index = start_index + limit
    lines = [
        {
            "step": entry.step,
            "level": entry.level,
            "service": entry.service,
            "message": entry.message,
        }
        for entry in entries[start_index:end_index]
    ]
    next_page = page + 1 if end_index < len(entries) else None
    return {"lines": lines, "next_page": next_page}


def tool_get_trace_sample(trace_id: str, scenario: Scenario) -> dict[str, Any]:
    """Return a synthetic trace sample."""

    sample = next(sample for sample in scenario.evidence.trace_samples if sample.trace_id == trace_id)
    return {
        "service": sample.service,
        "trace_id": sample.trace_id,
        "spans": [
            {
                "service": span.service,
                "operation": span.operation,
                "duration_ms": span.duration_ms,
                "status": span.status,
            }
            for span in sample.spans
        ],
        "error": sample.error,
        "duration_ms": sample.duration_ms,
    }


def tool_search_recent_deploys(
    service: str,
    window_steps: int,
    current_step: int,
    scenario: Scenario,
) -> dict[str, Any]:
    """Return deploy events inside the requested window."""

    start_step = current_step - window_steps + 1
    events = [
        {
            "service": event.service,
            "step": event.step,
            "from_version": event.from_version,
            "to_version": event.to_version,
            "author": event.author,
        }
        for event in scenario.evidence.deploy_history
        if event.service == service and start_step <= event.step <= current_step
    ]
    return {"events": events}


def tool_diff_config(
    service: str,
    from_version: str,
    to_version: str,
    scenario: Scenario,
) -> dict[str, Any]:
    """Return a structured config diff."""

    record = next(
        record
        for record in scenario.evidence.config_diffs
        if record.service == service
        and record.from_version == from_version
        and record.to_version == to_version
    )
    return {
        "service": service,
        "from_version": from_version,
        "to_version": to_version,
        "diff": [
            {"key": entry.key, "from": entry.from_value, "to": entry.to_value}
            for entry in record.diff
        ],
    }


def tool_view_runbook(service: str, section: str, scenario: Scenario) -> dict[str, Any]:
    """Return a runbook section as structured content."""

    return {
        "service": service,
        "section": section,
        "content": list(scenario.evidence.runbook_snippets[service][section]),
    }


def tool_request_help(team: str, scenario: Scenario) -> dict[str, Any]:
    """Return a deterministic team response."""

    return {"team": team, "response": scenario.evidence.help_responses[team]}
