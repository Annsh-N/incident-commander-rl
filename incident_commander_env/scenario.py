"""Scenario definitions and loading."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    metric_changes: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioEvidence:
    """Deterministic evidence returned by tools."""

    metrics_by_step: dict[str, tuple[float, ...]]
    logs_by_service: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class Scenario:
    """A single incident scenario."""

    id: str
    title: str
    description: str
    severity: str
    ground_truth_root_cause_id: str
    allowed_mitigations: list[str]
    forbidden_mitigations: list[str]
    timeline_events: list[TimelineEvent]
    evidence: ScenarioEvidence
    runbook_snippets: dict[str, str]


def _build_metric_series() -> dict[str, tuple[float, ...]]:
    error_rate = (
        6.8,
        7.6,
        8.9,
        9.5,
        9.1,
        8.7,
        8.4,
        8.0,
        7.8,
        7.5,
        7.2,
        7.0,
        6.8,
        6.7,
        6.5,
        6.4,
        6.3,
        6.2,
        6.1,
        6.0,
        5.9,
        5.8,
        5.7,
        5.7,
        5.6,
        5.6,
    )
    p95_latency = (
        1320.0,
        1480.0,
        1610.0,
        1685.0,
        1640.0,
        1595.0,
        1560.0,
        1520.0,
        1490.0,
        1450.0,
        1410.0,
        1385.0,
        1360.0,
        1340.0,
        1325.0,
        1310.0,
        1298.0,
        1286.0,
        1278.0,
        1265.0,
        1255.0,
        1248.0,
        1240.0,
        1235.0,
        1230.0,
        1225.0,
    )
    cpu = (
        58.0,
        60.0,
        62.0,
        63.0,
        61.0,
        60.0,
        59.0,
        58.0,
        57.0,
        56.0,
        56.0,
        55.0,
        55.0,
        54.0,
        54.0,
        53.0,
        53.0,
        52.0,
        52.0,
        51.0,
        51.0,
        50.0,
        50.0,
        50.0,
        49.0,
        49.0,
    )
    pricing_timeouts = (
        22.0,
        31.0,
        38.0,
        42.0,
        40.0,
        37.0,
        35.0,
        34.0,
        33.0,
        31.0,
        29.0,
        28.0,
        27.0,
        26.0,
        25.0,
        24.0,
        24.0,
        23.0,
        23.0,
        22.0,
        22.0,
        21.0,
        21.0,
        20.0,
        20.0,
        20.0,
    )
    return {
        "error_rate": error_rate,
        "p95_latency": p95_latency,
        "cpu": cpu,
        "pricing_timeouts": pricing_timeouts,
    }


def load_scenario() -> Scenario:
    """Return the hard-coded Stage 1 scenario."""

    evidence = ScenarioEvidence(
        metrics_by_step=_build_metric_series(),
        logs_by_service={
            "checkout-service": (
                "2026-03-12T14:00:01Z INFO Booting checkout-service version=v42",
                "2026-03-12T14:00:02Z INFO Loaded 18 feature flags successfully",
                "2026-03-12T14:00:05Z ERROR ENV PRICING_URL invalid: http://pricing:8080v1",
                "2026-03-12T14:00:06Z WARN Pricing client request timeout after 1500ms",
                "2026-03-12T14:00:09Z INFO Healthcheck completed in 42ms",
                "2026-03-12T14:00:12Z ERROR Failed to reach pricing-service endpoint from checkout-service",
                "2026-03-12T14:00:15Z INFO Request trace_id=abc123 cart fetch succeeded",
                "2026-03-12T14:00:18Z WARN Retrying pricing quote request due to upstream timeout",
                "2026-03-12T14:00:21Z INFO Worker heartbeat ok",
                "2026-03-12T14:00:25Z ERROR Checkout request failed with upstream pricing connection error",
            ),
            "pricing-service": (
                "2026-03-12T14:00:01Z INFO pricing-service ready",
                "2026-03-12T14:00:06Z INFO Received elevated timeout volume from checkout-service",
                "2026-03-12T14:00:08Z INFO CPU stable at 46%",
                "2026-03-12T14:00:12Z WARN Client timeouts increased for caller=checkout-service",
                "2026-03-12T14:00:16Z INFO Dependency cache refreshed",
            ),
        },
    )
    return Scenario(
        id="svc-checkout-regression",
        title="Checkout deployment regression",
        description=(
            "A new checkout-service deployment introduced a malformed PRICING_URL, "
            "causing downstream pricing requests to fail and checkout traffic to return 5xx errors."
        ),
        severity="sev-1",
        ground_truth_root_cause_id="checkout_pricing_url_misconfigured_after_v42_deploy",
        allowed_mitigations=[
            "rollback_checkout_v42_to_v41",
            "disable_new_pricing_path",
        ],
        forbidden_mitigations=[
            "restart_database",
            "scale_database",
            "purge_queue",
        ],
        timeline_events=[
            TimelineEvent(
                step=0,
                alerts=(
                    AlertDefinition(
                        id="alert-checkout-error-rate",
                        service="checkout-service",
                        signal="error_rate > 5%",
                    ),
                    AlertDefinition(
                        id="alert-checkout-p95-latency",
                        service="checkout-service",
                        signal="p95_latency > 1200ms",
                    ),
                    AlertDefinition(
                        id="alert-pricing-timeouts",
                        service="pricing-service",
                        signal="timeout_spikes > baseline",
                    ),
                ),
                messages=(
                    MessageDefinition(
                        ts_step=0,
                        sender="deploy-bot",
                        text="checkout-service v42 deployment completed 4 minutes ago.",
                    ),
                ),
            ),
            TimelineEvent(
                step=2,
                messages=(
                    MessageDefinition(
                        ts_step=2,
                        sender="support",
                        text="Support says customers can't complete checkout.",
                    ),
                ),
            ),
            TimelineEvent(
                step=6,
                messages=(
                    MessageDefinition(
                        ts_step=6,
                        sender="manager",
                        text="Manager asks for ETA.",
                    ),
                ),
            ),
        ],
        evidence=evidence,
        runbook_snippets={
            "checkout-service": (
                "If checkout 5xx after deploy: check PRICING_URL and rollback if misconfigured."
            ),
            "pricing-service": (
                "If pricing timeouts spike but pricing CPU is stable, inspect callers before scaling."
            ),
        },
    )
