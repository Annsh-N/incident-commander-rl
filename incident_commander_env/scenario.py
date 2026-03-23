"""Scenario loading and serialization for Stage 3."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AlertDefinition:
    """An alert shown to the agent."""

    id: str
    service: str
    signal: str
    active: bool = True


@dataclass(frozen=True)
class MessageDefinition:
    """A timeline message delivered to the agent."""

    ts_step: int
    sender: str
    text: str


@dataclass(frozen=True)
class TimelineEvent:
    """A step-keyed scenario event."""

    step: int
    alerts: tuple[AlertDefinition, ...] = ()
    messages: tuple[MessageDefinition, ...] = ()


@dataclass(frozen=True)
class ServiceDefinition:
    """Static metadata about a service."""

    name: str
    description: str
    dependencies: tuple[str, ...]
    owner: str
    initial_replicas: int = 2


@dataclass(frozen=True)
class MetricSeries:
    """Degraded and stabilized metric profiles."""

    degraded: tuple[float, ...]
    stabilized: tuple[float, ...]


@dataclass(frozen=True)
class LogEntry:
    """A deterministic synthetic log entry."""

    step: int
    service: str
    level: str
    message: str


@dataclass(frozen=True)
class DeployEvent:
    """A deploy event available to investigation tools."""

    service: str
    step: int
    from_version: str
    to_version: str
    author: str


@dataclass(frozen=True)
class ConfigDiffEntry:
    """A structured config diff entry."""

    key: str
    from_value: str
    to_value: str


@dataclass(frozen=True)
class ConfigDiffRecord:
    """A config diff between two versions."""

    service: str
    from_version: str
    to_version: str
    diff: tuple[ConfigDiffEntry, ...]


@dataclass(frozen=True)
class TraceSpan:
    """A synthetic trace span."""

    service: str
    operation: str
    duration_ms: float
    status: str


@dataclass(frozen=True)
class TraceSample:
    """A synthetic trace sample."""

    service: str
    trace_id: str
    spans: tuple[TraceSpan, ...]
    error: str | None
    duration_ms: float


@dataclass(frozen=True)
class UpdateRequirement:
    """A required communication update."""

    template_id: str
    audience: str


@dataclass(frozen=True)
class VerificationRequirement:
    """A required verification check."""

    service: str
    metric: str
    target: float
    window_steps: int


@dataclass(frozen=True)
class MitigationRule:
    """Maps a concrete action to a mitigation identifier."""

    mitigation_id: str
    action_type: str
    args_match: dict[str, Any]
    causal: bool
    forbidden: bool = False


@dataclass(frozen=True)
class ResolutionRubric:
    """Scenario-specific resolution requirements."""

    required_evidence_flags: tuple[str, ...]
    required_updates: tuple[UpdateRequirement, ...]
    required_verification: tuple[VerificationRequirement, ...]
    min_investigation_categories: int
    create_incident_by: int


@dataclass(frozen=True)
class ScenarioEvidence:
    """Deterministic scenario evidence used by tools."""

    services: dict[str, ServiceDefinition]
    metric_profiles: dict[str, dict[str, MetricSeries]]
    logs_by_service: dict[str, tuple[LogEntry, ...]]
    deploy_history: tuple[DeployEvent, ...]
    config_diffs: tuple[ConfigDiffRecord, ...]
    trace_samples: tuple[TraceSample, ...]
    runbook_snippets: dict[str, dict[str, tuple[str, ...]]]
    help_responses: dict[str, str]


@dataclass(frozen=True)
class Scenario:
    """A single incident scenario or deterministic variant."""

    id: str
    title: str
    description: str
    severity: str
    ground_truth_root_cause_id: str
    allowed_mitigations: list[str]
    safe_mitigations: list[str]
    forbidden_mitigations: list[str]
    all_mitigations: list[str]
    patch_ids: dict[str, tuple[str, ...]]
    feature_flags: dict[str, bool]
    deploy_versions: dict[str, str]
    config_versions: dict[str, str]
    timeline_events: list[TimelineEvent]
    evidence: ScenarioEvidence
    mitigation_rules: tuple[MitigationRule, ...]
    causal_action_sets: tuple[tuple[str, ...], ...]
    resolution_rubric: ResolutionRubric
    evidence_markers: dict[str, Any]
    variant_of: str | None = None
    variant_seed: int | None = None
    variant_ops: tuple[str, ...] = ()


SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


def _tuple_of_strings(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(values)


def _load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _metric_profiles_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, MetricSeries]]:
    profiles: dict[str, dict[str, MetricSeries]] = {}
    for service, metrics in payload.items():
        profiles[service] = {}
        for metric_name, series_payload in metrics.items():
            profiles[service][metric_name] = MetricSeries(
                degraded=tuple(float(value) for value in series_payload["degraded"]),
                stabilized=tuple(float(value) for value in series_payload["stabilized"]),
            )
    return profiles


def _scenario_from_payload(payload: dict[str, Any]) -> Scenario:
    services = {
        item["name"]: ServiceDefinition(
            name=item["name"],
            description=item["description"],
            dependencies=tuple(item["dependencies"]),
            owner=item["owner"],
            initial_replicas=int(item.get("initial_replicas", 2)),
        )
        for item in payload["services"]
    }
    timeline_events = [
        TimelineEvent(
            step=int(event["step"]),
            alerts=tuple(
                AlertDefinition(
                    id=alert["id"],
                    service=alert["service"],
                    signal=alert["signal"],
                    active=bool(alert.get("active", True)),
                )
                for alert in event.get("alerts", [])
            ),
            messages=tuple(
                MessageDefinition(
                    ts_step=int(message["ts_step"]),
                    sender=message["sender"],
                    text=message["text"],
                )
                for message in event.get("messages", [])
            ),
        )
        for event in payload["timeline_events"]
    ]
    evidence_payload = payload["evidence"]
    evidence = ScenarioEvidence(
        services=services,
        metric_profiles=_metric_profiles_from_payload(evidence_payload["metrics"]),
        logs_by_service={
            service: tuple(
                LogEntry(
                    step=int(entry["step"]),
                    service=entry["service"],
                    level=entry["level"],
                    message=entry["message"],
                )
                for entry in entries
            )
            for service, entries in evidence_payload["logs"].items()
        },
        deploy_history=tuple(
            DeployEvent(
                service=event["service"],
                step=int(event["step"]),
                from_version=event["from_version"],
                to_version=event["to_version"],
                author=event["author"],
            )
            for event in evidence_payload["deploy_history"]
        ),
        config_diffs=tuple(
            ConfigDiffRecord(
                service=record["service"],
                from_version=record["from_version"],
                to_version=record["to_version"],
                diff=tuple(
                    ConfigDiffEntry(
                        key=entry["key"],
                        from_value=entry["from"],
                        to_value=entry["to"],
                    )
                    for entry in record["diff"]
                ),
            )
            for record in evidence_payload["config_diffs"]
        ),
        trace_samples=tuple(
            TraceSample(
                service=sample["service"],
                trace_id=sample["trace_id"],
                spans=tuple(
                    TraceSpan(
                        service=span["service"],
                        operation=span["operation"],
                        duration_ms=float(span["duration_ms"]),
                        status=span["status"],
                    )
                    for span in sample["spans"]
                ),
                error=sample.get("error"),
                duration_ms=float(sample["duration_ms"]),
            )
            for sample in evidence_payload["trace_samples"]
        ),
        runbook_snippets={
            service: {
                section: tuple(lines)
                for section, lines in sections.items()
            }
            for service, sections in evidence_payload["runbook_snippets"].items()
        },
        help_responses=dict(evidence_payload["help_responses"]),
    )
    mitigation_rules = tuple(
        MitigationRule(
            mitigation_id=rule["mitigation_id"],
            action_type=rule["action_type"],
            args_match=dict(rule["args_match"]),
            causal=bool(rule["causal"]),
            forbidden=bool(rule.get("forbidden", False)),
        )
        for rule in payload["mitigation_rules"]
    )
    rubric_payload = payload["resolution_rubric"]
    resolution_rubric = ResolutionRubric(
        required_evidence_flags=tuple(rubric_payload["required_evidence_flags"]),
        required_updates=tuple(
            UpdateRequirement(
                template_id=requirement["template_id"],
                audience=requirement["audience"],
            )
            for requirement in rubric_payload["required_updates"]
        ),
        required_verification=tuple(
            VerificationRequirement(
                service=requirement["service"],
                metric=requirement["metric"],
                target=float(requirement["target"]),
                window_steps=int(requirement["window_steps"]),
            )
            for requirement in rubric_payload["required_verification"]
        ),
        min_investigation_categories=int(rubric_payload["min_investigation_categories"]),
        create_incident_by=int(rubric_payload["create_incident_by"]),
    )
    return Scenario(
        id=payload["id"],
        title=payload["title"],
        description=payload["description"],
        severity=payload["severity"],
        ground_truth_root_cause_id=payload["ground_truth_root_cause_id"],
        allowed_mitigations=list(payload["allowed_mitigations"]),
        safe_mitigations=list(payload["safe_mitigations"]),
        forbidden_mitigations=list(payload["forbidden_mitigations"]),
        all_mitigations=list(payload["all_mitigations"]),
        patch_ids={
            service: tuple(values)
            for service, values in payload["patch_ids"].items()
        },
        feature_flags=dict(payload["feature_flags"]),
        deploy_versions=dict(payload["deploy_versions"]),
        config_versions=dict(payload["config_versions"]),
        timeline_events=timeline_events,
        evidence=evidence,
        mitigation_rules=mitigation_rules,
        causal_action_sets=tuple(tuple(group) for group in payload["causal_action_sets"]),
        resolution_rubric=resolution_rubric,
        evidence_markers=dict(payload["evidence_markers"]),
        variant_of=payload.get("variant_of"),
        variant_seed=payload.get("variant_seed"),
        variant_ops=tuple(payload.get("variant_ops", [])),
    )


def scenario_to_payload(scenario: Scenario) -> dict[str, Any]:
    """Convert a Scenario dataclass into a JSON-serializable payload."""

    payload = asdict(scenario)
    services = []
    for service in scenario.evidence.services.values():
        services.append(
            {
                "name": service.name,
                "description": service.description,
                "dependencies": list(service.dependencies),
                "owner": service.owner,
                "initial_replicas": service.initial_replicas,
            }
        )
    payload["services"] = services
    evidence = payload.pop("evidence")
    metrics_payload: dict[str, Any] = {}
    for service, metric_map in scenario.evidence.metric_profiles.items():
        metrics_payload[service] = {}
        for metric_name, series in metric_map.items():
            metrics_payload[service][metric_name] = {
                "degraded": list(series.degraded),
                "stabilized": list(series.stabilized),
            }
    evidence_payload = {
        "metrics": metrics_payload,
        "logs": {
            service: [asdict(entry) for entry in entries]
            for service, entries in scenario.evidence.logs_by_service.items()
        },
        "deploy_history": [asdict(entry) for entry in scenario.evidence.deploy_history],
        "config_diffs": [
            {
                "service": record.service,
                "from_version": record.from_version,
                "to_version": record.to_version,
                "diff": [
                    {"key": entry.key, "from": entry.from_value, "to": entry.to_value}
                    for entry in record.diff
                ],
            }
            for record in scenario.evidence.config_diffs
        ],
        "trace_samples": [asdict(sample) for sample in scenario.evidence.trace_samples],
        "runbook_snippets": {
            service: {section: list(lines) for section, lines in sections.items()}
            for service, sections in scenario.evidence.runbook_snippets.items()
        },
        "help_responses": dict(scenario.evidence.help_responses),
    }
    payload["evidence"] = evidence_payload
    payload["timeline_events"] = [
        {
            "step": event.step,
            "alerts": [asdict(alert) for alert in event.alerts],
            "messages": [asdict(message) for message in event.messages],
        }
        for event in scenario.timeline_events
    ]
    payload["mitigation_rules"] = [
        {
            "mitigation_id": rule.mitigation_id,
            "action_type": rule.action_type,
            "args_match": dict(rule.args_match),
            "causal": rule.causal,
            "forbidden": rule.forbidden,
        }
        for rule in scenario.mitigation_rules
    ]
    payload["causal_action_sets"] = [list(group) for group in scenario.causal_action_sets]
    payload["resolution_rubric"] = {
        "required_evidence_flags": list(scenario.resolution_rubric.required_evidence_flags),
        "required_updates": [
            asdict(requirement) for requirement in scenario.resolution_rubric.required_updates
        ],
        "required_verification": [
            asdict(requirement) for requirement in scenario.resolution_rubric.required_verification
        ],
        "min_investigation_categories": scenario.resolution_rubric.min_investigation_categories,
        "create_incident_by": scenario.resolution_rubric.create_incident_by,
    }
    payload["evidence_markers"] = dict(scenario.evidence_markers)
    return payload


def load_base_scenarios() -> list[Scenario]:
    """Load all base scenarios from disk."""

    scenarios = [
        _scenario_from_payload(_load_payload(path))
        for path in sorted(SCENARIOS_DIR.glob("*.json"))
    ]
    if not scenarios:
        raise FileNotFoundError(f"No scenarios found in {SCENARIOS_DIR}")
    return scenarios


def load_scenario(scenario_id: str | None = None) -> Scenario:
    """Load one base scenario by id, defaulting to the first scenario."""

    scenarios = load_base_scenarios()
    if scenario_id is None:
        return scenarios[0]
    for scenario in scenarios:
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario_id: {scenario_id}")
