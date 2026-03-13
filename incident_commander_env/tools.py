"""Deterministic tool simulators."""

from __future__ import annotations

from typing import Any

from .scenario import Scenario


def tool_get_metrics(
    metric: str,
    window: int,
    current_step: int,
    scenario: Scenario,
) -> dict[str, Any]:
    """Return a stable metric window ending at the current step."""

    series = scenario.evidence.metrics_by_step[metric]
    end_index = min(current_step, len(series) - 1)
    start_index = max(0, end_index - window + 1)
    values = list(series[start_index : end_index + 1])
    return {
        "metric": metric,
        "window": window,
        "start_step": start_index,
        "end_step": end_index,
        "series": values,
        "current": values[-1],
    }


def tool_get_logs(
    service: str,
    query: str,
    limit: int,
    page: int,
    scenario: Scenario,
) -> dict[str, Any]:
    """Return paged logs filtered by a case-insensitive substring."""

    source_lines = scenario.evidence.logs_by_service[service]
    lowered_query = query.casefold()
    filtered_lines = [
        line for line in source_lines if lowered_query in line.casefold()
    ] if lowered_query else list(source_lines)

    start_index = (page - 1) * limit
    end_index = start_index + limit
    lines = filtered_lines[start_index:end_index]
    next_page = page + 1 if end_index < len(filtered_lines) else None
    return {"lines": lines, "next_page": next_page}


def tool_view_runbook(service: str, scenario: Scenario) -> str:
    """Return the deterministic runbook snippet for a service."""

    return scenario.runbook_snippets[service]
