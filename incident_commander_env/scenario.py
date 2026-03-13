"""Scenario definitions and loading for the Incident Commander environment."""

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


@dataclass(frozen=True)
class ServiceDefinition:
    """Static metadata about a service."""

    name: str
    description: str
    dependencies: tuple[str, ...]
    owner: str


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
class ScenarioEvidence:
    """Deterministic scenario evidence used by tools."""

    services: dict[str, ServiceDefinition]
    degraded_metrics: dict[str, dict[str, tuple[float, ...]]]
    stabilized_metrics: dict[str, dict[str, tuple[float, ...]]]
    logs_by_service: dict[str, tuple[LogEntry, ...]]
    deploy_history: tuple[DeployEvent, ...]
    config_diffs: dict[str, dict[tuple[str, str], tuple[ConfigDiffEntry, ...]]]
    trace_samples: dict[str, TraceSample]
    runbook_snippets: dict[str, dict[str, tuple[str, ...]]]
    help_responses: dict[str, str]


@dataclass(frozen=True)
class Scenario:
    """A single incident scenario."""

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


def load_scenario() -> Scenario:
    """Return the hard-coded Stage 2 scenario."""

    services = {
        "checkout-service": ServiceDefinition(
            name="checkout-service",
            description="Customer-facing checkout API handling cart submission and pricing lookups.",
            dependencies=("pricing-service", "orders-db"),
            owner="payments",
        ),
        "pricing-service": ServiceDefinition(
            name="pricing-service",
            description="Internal service that calculates cart pricing and discounts.",
            dependencies=("orders-db",),
            owner="pricing",
        ),
        "orders-db": ServiceDefinition(
            name="orders-db",
            description="Primary database for order and cart persistence.",
            dependencies=(),
            owner="db",
        ),
    }

    degraded_metrics = {
        "checkout-service": {
            "error_rate": (6.8, 7.6, 8.8, 9.2, 9.0, 8.7, 8.4, 8.2, 8.0, 7.8, 7.7, 7.6),
            "p95_latency": (
                1320.0,
                1480.0,
                1595.0,
                1660.0,
                1635.0,
                1600.0,
                1560.0,
                1535.0,
                1510.0,
                1490.0,
                1475.0,
                1460.0,
            ),
            "cpu": (58.0, 61.0, 63.0, 64.0, 63.0, 62.0, 61.0, 60.0, 60.0, 59.0, 59.0, 58.0),
            "queue_depth": (24.0, 32.0, 40.0, 46.0, 44.0, 42.0, 40.0, 39.0, 37.0, 36.0, 35.0, 35.0),
        },
        "pricing-service": {
            "pricing_timeouts": (22.0, 31.0, 38.0, 42.0, 41.0, 39.0, 37.0, 36.0, 34.0, 33.0, 32.0, 31.0),
            "cpu": (46.0, 47.0, 48.0, 49.0, 48.0, 48.0, 47.0, 47.0, 46.0, 46.0, 45.0, 45.0),
        },
        "orders-db": {
            "db_conn": (64.0, 66.0, 67.0, 69.0, 68.0, 68.0, 67.0, 67.0, 66.0, 66.0, 65.0, 65.0),
            "cpu": (38.0, 39.0, 39.0, 40.0, 40.0, 39.0, 39.0, 39.0, 38.0, 38.0, 38.0, 37.0),
        },
    }

    stabilized_metrics = {
        "checkout-service": {
            "error_rate": (3.2, 1.8, 1.1, 0.8, 0.6, 0.6),
            "p95_latency": (920.0, 640.0, 510.0, 470.0, 450.0, 445.0),
            "cpu": (56.0, 53.0, 50.0, 48.0, 47.0, 47.0),
            "queue_depth": (22.0, 15.0, 9.0, 6.0, 5.0, 5.0),
        },
        "pricing-service": {
            "pricing_timeouts": (10.0, 4.0, 2.0, 1.0, 1.0, 1.0),
            "cpu": (45.0, 44.0, 43.0, 43.0, 42.0, 42.0),
        },
        "orders-db": {
            "db_conn": (63.0, 62.0, 61.0, 60.0, 60.0, 60.0),
            "cpu": (37.0, 37.0, 36.0, 36.0, 36.0, 35.0),
        },
    }

    logs_by_service = {
        "checkout-service": (
            LogEntry(step=0, service="checkout-service", level="INFO", message="Booting checkout-service version=v42"),
            LogEntry(step=0, service="checkout-service", level="INFO", message="Loaded 18 feature flags successfully"),
            LogEntry(step=0, service="checkout-service", level="WARN", message="Retry budget increased for guest checkouts"),
            LogEntry(step=0, service="checkout-service", level="INFO", message="Cart hydration completed trace_id=trace-bootstrap"),
            LogEntry(step=1, service="checkout-service", level="WARN", message="pricing client timeout caller=checkout-service retry=1"),
            LogEntry(step=1, service="checkout-service", level="INFO", message="Worker heartbeat ok shard=3"),
            LogEntry(step=1, service="checkout-service", level="ERROR", message="ENV PRICING_URL invalid: http://pricing:8080v1"),
            LogEntry(step=1, service="checkout-service", level="ERROR", message="checkout request failed cause=pricing timeout trace_id=trace-001"),
            LogEntry(step=2, service="checkout-service", level="WARN", message="upstream pricing timeout duration_ms=1500 trace_id=trace-002"),
            LogEntry(step=2, service="checkout-service", level="INFO", message="abandoned cart worker flush completed"),
            LogEntry(step=3, service="checkout-service", level="WARN", message="queue lag detected but within threshold"),
            LogEntry(step=3, service="checkout-service", level="INFO", message="request trace_id=trace-003 cart fetch succeeded"),
        ),
        "pricing-service": (
            LogEntry(step=0, service="pricing-service", level="INFO", message="pricing-service ready"),
            LogEntry(step=1, service="pricing-service", level="WARN", message="client timeouts increased caller=checkout-service"),
            LogEntry(step=2, service="pricing-service", level="INFO", message="cpu stable at 46%"),
            LogEntry(step=2, service="pricing-service", level="WARN", message="upstream callers timing out before response completion"),
        ),
        "orders-db": (
            LogEntry(step=0, service="orders-db", level="INFO", message="connection pool healthy active=64"),
            LogEntry(step=2, service="orders-db", level="INFO", message="query latency stable p95=12ms"),
        ),
    }

    deploy_history = (
        DeployEvent(
            service="checkout-service",
            step=0,
            from_version="v41",
            to_version="v42",
            author="deploy-bot",
        ),
        DeployEvent(
            service="pricing-service",
            step=-3,
            from_version="v16",
            to_version="v17",
            author="deploy-bot",
        ),
    )

    config_diffs = {
        "checkout-service": {
            ("v41", "v42"): (
                ConfigDiffEntry(
                    key="PRICING_URL",
                    from_value="http://pricing:8080/v1",
                    to_value="http://pricing:8080v1",
                ),
                ConfigDiffEntry(
                    key="NEW_PRICING_PATH_ENABLED",
                    from_value="false",
                    to_value="true",
                ),
                ConfigDiffEntry(
                    key="MAX_CART_RETRIES",
                    from_value="2",
                    to_value="1",
                ),
            )
        }
    }

    trace_samples = {
        "trace-001": TraceSample(
            service="checkout-service",
            trace_id="trace-001",
            spans=(
                TraceSpan("checkout-service", "POST /checkout", 1620.0, "error"),
                TraceSpan("pricing-service", "GET /price", 1495.0, "timeout"),
                TraceSpan("orders-db", "SELECT cart", 14.0, "ok"),
            ),
            error="pricing timeout propagated to checkout",
            duration_ms=1620.0,
        ),
        "trace-002": TraceSample(
            service="checkout-service",
            trace_id="trace-002",
            spans=(
                TraceSpan("checkout-service", "POST /checkout", 1510.0, "error"),
                TraceSpan("pricing-service", "GET /price", 1488.0, "timeout"),
            ),
            error="upstream timeout contacting pricing-service",
            duration_ms=1510.0,
        ),
    }

    runbook_snippets = {
        "checkout-service": {
            "triage": (
                "Check recent deploys before scaling the service.",
                "Compare checkout config and feature flags when 5xx spikes after deploy.",
            ),
            "mitigation": (
                "Rollback checkout or disable the new pricing path if pricing requests fail after deploy.",
                "Restarting checkout may reduce noise but will not fix bad config.",
            ),
            "verification": (
                "Confirm checkout error_rate and p95_latency recover after the mitigation.",
                "Run a health check and verify pricing timeout symptoms subside.",
            ),
        },
        "pricing-service": {
            "triage": (
                "If pricing CPU is stable but callers time out, inspect caller configuration first.",
            ),
            "mitigation": (
                "Avoid scaling pricing until caller-side regressions are ruled out.",
            ),
            "verification": (
                "Confirm timeout volume drops after caller remediation.",
            ),
        },
    }

    help_responses = {
        "db": "DB team reports connection pool and query latency are normal; no evidence of database saturation.",
        "network": "Network team sees no packet loss between checkout and pricing; issue appears application-level.",
        "pricing": "Pricing team sees caller timeouts from checkout and suggests validating checkout endpoint configuration.",
        "platform": "Platform team suggests checking the most recent checkout deploy and diffing env vars before scaling.",
    }

    evidence = ScenarioEvidence(
        services=services,
        degraded_metrics=degraded_metrics,
        stabilized_metrics=stabilized_metrics,
        logs_by_service=logs_by_service,
        deploy_history=deploy_history,
        config_diffs=config_diffs,
        trace_samples=trace_samples,
        runbook_snippets=runbook_snippets,
        help_responses=help_responses,
    )

    return Scenario(
        id="svc-checkout-regression",
        title="Checkout deploy regression with downstream pricing timeouts",
        description=(
            "checkout-service v42 introduced a malformed PRICING_URL configuration. "
            "The resulting pricing call failures manifest as checkout 5xx errors, latency inflation, "
            "and secondary pricing timeout alerts, with database and queue signals acting as distractors."
        ),
        severity="sev1",
        ground_truth_root_cause_id="checkout_pricing_url_misconfigured_after_v42_deploy",
        allowed_mitigations=[
            "rollback_checkout_v42_to_v41",
            "disable_new_pricing_path",
            "revert_pricing_url_config",
        ],
        safe_mitigations=[
            "rollback_checkout_v42_to_v41",
            "disable_new_pricing_path",
            "revert_pricing_url_config",
            "restart_checkout_service",
            "scale_checkout_service",
        ],
        forbidden_mitigations=[
            "restart_database",
            "scale_database",
            "purge_queue",
        ],
        all_mitigations=[
            "rollback_checkout_v42_to_v41",
            "disable_new_pricing_path",
            "revert_pricing_url_config",
            "restart_checkout_service",
            "scale_checkout_service",
            "restart_database",
            "scale_database",
            "purge_queue",
        ],
        patch_ids={"checkout-service": ("fix_pricing_url_v42", "bump_retry_budget")},
        feature_flags={"new_pricing_path": True},
        deploy_versions={
            "checkout-service": "v42",
            "pricing-service": "v17",
            "orders-db": "db-2026-03-08",
        },
        config_versions={
            "checkout-service": "v42",
            "pricing-service": "v17",
            "orders-db": "db-2026-03-08",
        },
        timeline_events=[
            TimelineEvent(
                step=0,
                alerts=(
                    AlertDefinition("alert-checkout-error-rate", "checkout-service", "error_rate > 5%"),
                    AlertDefinition("alert-checkout-p95-latency", "checkout-service", "p95_latency > 1200ms"),
                    AlertDefinition("alert-pricing-timeouts", "pricing-service", "pricing_timeouts > baseline"),
                ),
                messages=(
                    MessageDefinition(0, "deploy-bot", "checkout-service v42 deployment completed 4 minutes ago."),
                ),
            ),
            TimelineEvent(
                step=2,
                messages=(
                    MessageDefinition(2, "support", "Support says customers can't complete checkout."),
                ),
            ),
            TimelineEvent(
                step=6,
                messages=(
                    MessageDefinition(6, "manager", "Manager asks for ETA."),
                ),
            ),
        ],
        evidence=evidence,
    )
