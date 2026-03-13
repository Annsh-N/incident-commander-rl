"""Main Incident Commander environment."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from random import Random
from typing import Any

from .observation import build_observation
from .replay import ReplayBuffer
from .scenario import Scenario, load_scenario
from .scorer import score_step
from .tools import (
    tool_describe_service,
    tool_diff_config,
    tool_get_logs,
    tool_get_metrics,
    tool_get_trace_sample,
    tool_list_services,
    tool_request_help,
    tool_search_recent_deploys,
    tool_view_runbook,
)
from .validation import validate_action


@dataclass
class AlertState:
    """Mutable alert state inside the environment."""

    id: str
    service: str
    signal: str
    active: bool = True
    acknowledged: bool = False


@dataclass
class MessageRecord:
    """Messages delivered to the agent."""

    ts_step: int
    sender: str
    text: str


@dataclass
class LogPageRecord:
    """Stored log query results."""

    step: int
    service: str
    query: str
    window_steps: int
    limit: int
    page: int
    lines: list[dict[str, Any]]
    next_page: int | None


@dataclass
class EnvState:
    """Environment state."""

    current_step: int
    scenario_id: str
    incident_status: str
    active_alerts: list[AlertState]
    message_feed: list[MessageRecord]
    metrics: dict[str, dict[str, list[float]]]
    logs: list[LogPageRecord]
    applied_actions: list[dict[str, Any]]
    scenario: Scenario
    incident_created: bool = False
    incident_severity: str | None = None
    roles_assigned: dict[str, str] = field(default_factory=dict)
    last_update_step: int | None = None
    updates_posted: list[dict[str, Any]] = field(default_factory=list)
    mitigations_applied: list[str] = field(default_factory=list)
    proposed_mitigations: list[str] = field(default_factory=list)
    executed_changes: list[dict[str, Any]] = field(default_factory=list)
    unsafe_attempt: bool = False
    config_state: dict[str, str] = field(default_factory=dict)
    deploy_versions: dict[str, str] = field(default_factory=dict)
    feature_flags: dict[str, bool] = field(default_factory=dict)
    service_replicas: dict[str, int] = field(default_factory=dict)
    service_restarts: dict[str, int] = field(default_factory=dict)
    service_health: dict[str, str] = field(default_factory=dict)
    resolved_state: bool = False
    causal_mitigation_id: str | None = None
    causal_fix_step: int | None = None
    causal_change_planned: bool = False
    causal_change_evidence_met: bool = False
    last_executed_mitigation_id: str | None = None
    confirmations: dict[str, bool] = field(default_factory=dict)
    evidence_flags: dict[str, bool] = field(default_factory=dict)
    last_tool_results: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    action_signature_counts: dict[str, int] = field(default_factory=dict)
    core_tool_rewarded: dict[str, bool] = field(default_factory=dict)
    rewards_claimed: dict[str, bool] = field(default_factory=dict)
    seed: int | None = None


class IncidentCommanderEnv:
    """Deterministic RL environment with a Gymnasium-like API."""

    def __init__(self, max_steps: int = 25, scenario: Scenario | None = None) -> None:
        self.max_steps = max_steps
        self.scenario = scenario or load_scenario()
        self.state: EnvState | None = None
        self._done = False
        self._rng = Random(0)
        self._replay = ReplayBuffer(entries=[])

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        """Reset the environment and return the initial observation."""

        self._rng = Random(seed if seed is not None else 0)
        scenario = self.scenario
        metrics = {
            service: {metric: [] for metric in metric_map.keys()}
            for service, metric_map in scenario.evidence.degraded_metrics.items()
        }
        self.state = EnvState(
            current_step=0,
            scenario_id=scenario.id,
            incident_status="active",
            active_alerts=[],
            message_feed=[],
            metrics=metrics,
            logs=[],
            applied_actions=[],
            scenario=scenario,
            config_state=dict(scenario.config_versions),
            deploy_versions=dict(scenario.deploy_versions),
            feature_flags=dict(scenario.feature_flags),
            service_replicas={
                "checkout-service": 6,
                "pricing-service": 4,
                "orders-db": 1,
            },
            service_restarts={
                "checkout-service": 0,
                "pricing-service": 0,
                "orders-db": 0,
            },
            confirmations={"error_rate": False, "p95_latency": False},
            evidence_flags={
                "saw_deploy": False,
                "saw_config_diff": False,
                "saw_key_log": False,
                "saw_timeout_trace": False,
            },
            last_tool_results={
                "metrics": None,
                "logs": None,
                "deploys": None,
                "diff": None,
                "trace": None,
                "runbook": None,
                "health": None,
            },
            core_tool_rewarded={"metrics": False, "logs": False, "deploy_config": False},
            rewards_claimed={
                "incident_created_early": False,
                "initial_internal_update": False,
                "status_update_after_mitigation": False,
            },
            seed=seed,
        )
        self._done = False
        self._replay.reset()
        self._apply_timeline_events(0)
        self._append_metrics_for_step(0)
        self._refresh_service_health()
        return build_observation(self.state, scenario)

    def step(
        self, action: dict[str, Any]
    ) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        """Apply one environment action."""

        if self.state is None:
            raise RuntimeError("reset must be called before step")
        if self._done:
            raise RuntimeError("cannot step a finished episode")

        info: dict[str, Any] = {
            "valid_action": False,
            "error": None,
            "applied": False,
            "resolution": None,
            "debug": [],
            "tool_result": None,
        }

        action_copy = deepcopy(action)
        action_type = action_copy.get("type") if isinstance(action_copy, dict) else None
        is_valid, error = validate_action(action_copy, self.state)
        done = False

        if not is_valid:
            reward = -0.12
            info["error"] = error
            info["debug"].append(error or "validation failed")
            if action_type in {"declare_resolved", "declare_failed"}:
                done = True
                self.state.incident_status = "failed"
                info["resolution"] = "failed"
        else:
            info["valid_action"] = True
            self.state.applied_actions.append(action_copy)
            tool_result, applied = self._apply_action(action_copy)
            info["tool_result"] = tool_result
            info["applied"] = applied
            reward, scored_done, score_info = score_step(
                self.state, action_copy, tool_result, self.scenario
            )
            info.update({key: value for key, value in score_info.items() if key not in {"debug"}})
            info["debug"].extend(score_info.get("debug", []))
            done = scored_done

            if info["resolution"] == "success":
                self.state.incident_status = "resolved"
            elif done:
                self.state.incident_status = "failed"

        if not done:
            advance_by = 1
            if is_valid and action_copy["type"] == "wait":
                advance_by = action_copy["args"]["steps"]
            self._advance_time(advance_by)
            if self.state.current_step >= self.max_steps:
                done = True
                self.state.incident_status = "failed"
                info["resolution"] = info["resolution"] or "timeout"
                info.setdefault("failure_reasons", [])
                info["failure_reasons"].append("timeout_exhausted")
                info["debug"].append("Max steps reached before stable resolution.")

        reward = round(reward, 10)
        observation = build_observation(self.state, self.scenario)
        self._done = done
        self._replay.append(
            step=self.state.current_step,
            observation=observation,
            action=action_copy,
            reward=reward,
            done=done,
            info=info,
        )
        return observation, reward, done, info

    def get_replay(self) -> list[dict[str, Any]]:
        """Return a copy of the replay buffer."""

        return self._replay.as_list()

    def _apply_timeline_events(self, step: int) -> None:
        assert self.state is not None
        for event in self.scenario.timeline_events:
            if event.step != step:
                continue
            for alert in event.alerts:
                existing = next(
                    (candidate for candidate in self.state.active_alerts if candidate.id == alert.id),
                    None,
                )
                if existing is None:
                    self.state.active_alerts.append(
                        AlertState(
                            id=alert.id,
                            service=alert.service,
                            signal=alert.signal,
                            active=alert.active,
                        )
                    )
                else:
                    existing.active = alert.active
            for message in event.messages:
                self.state.message_feed.append(
                    MessageRecord(
                        ts_step=message.ts_step,
                        sender=message.sender,
                        text=message.text,
                    )
                )

    def _advance_time(self, steps: int) -> None:
        assert self.state is not None
        for _ in range(steps):
            if self.state.current_step >= self.max_steps:
                break
            self.state.current_step += 1
            self._apply_timeline_events(self.state.current_step)
            self._append_metrics_for_step(self.state.current_step)
            self._refresh_service_health()
            self._refresh_resolved_state()

    def _append_metrics_for_step(self, step: int) -> None:
        assert self.state is not None
        for service, metric_map in self.state.metrics.items():
            for metric_name, series in metric_map.items():
                series.append(self._compute_metric_value(service, metric_name, step))

    def _compute_metric_value(self, service: str, metric: str, step: int) -> float:
        assert self.state is not None
        degraded = self.scenario.evidence.degraded_metrics[service][metric]
        degraded_value = float(degraded[min(step, len(degraded) - 1)])

        if self.state.causal_fix_step is not None and step > self.state.causal_fix_step:
            stabilized = self.scenario.evidence.stabilized_metrics[service][metric]
            offset = step - self.state.causal_fix_step - 1
            return float(stabilized[min(offset, len(stabilized) - 1)])

        if self.state.last_executed_mitigation_id is not None:
            latest = self.state.last_executed_mitigation_id
            if latest == "restart_checkout_service" and service == "checkout-service":
                if metric == "cpu":
                    return max(45.0, degraded_value - 4.0)
                if metric == "p95_latency":
                    return degraded_value - 80.0
            if latest == "scale_checkout_service" and service == "checkout-service":
                if metric == "p95_latency":
                    return degraded_value - 120.0
                if metric == "error_rate":
                    return max(5.5, degraded_value - 0.3)
        return degraded_value

    def _refresh_service_health(self) -> None:
        assert self.state is not None
        checkout_error = self.state.metrics["checkout-service"]["error_rate"][-1]
        checkout_latency = self.state.metrics["checkout-service"]["p95_latency"][-1]
        pricing_timeouts = self.state.metrics["pricing-service"]["pricing_timeouts"][-1]
        db_conn = self.state.metrics["orders-db"]["db_conn"][-1]

        self.state.service_health = {
            "checkout-service": "healthy"
            if checkout_error < 2.0 and checkout_latency < 700.0
            else "degraded",
            "pricing-service": "healthy" if pricing_timeouts < 5.0 else "degraded",
            "orders-db": "healthy" if db_conn < 80.0 else "degraded",
        }

    def _refresh_resolved_state(self) -> None:
        assert self.state is not None
        waited_after_fix = (
            self.state.causal_fix_step is not None and self.state.current_step > self.state.causal_fix_step
        )
        metrics_confirmed = self.state.confirmations["error_rate"] and self.state.confirmations["p95_latency"]
        self.state.resolved_state = bool(
            self.state.causal_mitigation_id
            and self.state.causal_change_planned
            and self.state.causal_change_evidence_met
            and waited_after_fix
            and metrics_confirmed
        )

    def _apply_action(self, action: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
        assert self.state is not None
        action_type = action["type"]
        args = action["args"]
        tool_result: dict[str, Any] | None = None
        applied = True

        if action_type == "ack_alert":
            alert = next(alert for alert in self.state.active_alerts if alert.id == args["alert_id"])
            applied = not alert.acknowledged
            alert.acknowledged = True
            return None, applied

        if action_type == "list_services":
            tool_result = tool_list_services(self.scenario)
        elif action_type == "describe_service":
            tool_result = tool_describe_service(args["service"], self.state, self.scenario)
        elif action_type == "get_metrics":
            tool_result = tool_get_metrics(
                service=args["service"],
                metric=args["metric"],
                window_steps=args["window_steps"],
                agg=args["agg"],
                env_state=self.state,
            )
            self.state.last_tool_results["metrics"] = tool_result
        elif action_type == "get_logs":
            tool_result = tool_get_logs(
                service=args["service"],
                query=args["query"],
                window_steps=args["window_steps"],
                limit=args["limit"],
                page=args["page"],
                current_step=self.state.current_step,
                scenario=self.scenario,
            )
            self.state.logs.append(
                LogPageRecord(
                    step=self.state.current_step,
                    service=args["service"],
                    query=args["query"],
                    window_steps=args["window_steps"],
                    limit=args["limit"],
                    page=args["page"],
                    lines=list(tool_result["lines"]),
                    next_page=tool_result["next_page"],
                )
            )
            self.state.last_tool_results["logs"] = tool_result
        elif action_type == "get_trace_sample":
            tool_result = tool_get_trace_sample(args["trace_id"], self.scenario)
            self.state.last_tool_results["trace"] = tool_result
        elif action_type == "search_recent_deploys":
            tool_result = tool_search_recent_deploys(
                service=args["service"],
                window_steps=args["window_steps"],
                current_step=self.state.current_step,
                scenario=self.scenario,
            )
            self.state.last_tool_results["deploys"] = tool_result
        elif action_type == "diff_config":
            tool_result = tool_diff_config(
                service=args["service"],
                from_version=args["from_version"],
                to_version=args["to_version"],
                scenario=self.scenario,
            )
            self.state.last_tool_results["diff"] = tool_result
        elif action_type == "view_runbook":
            tool_result = tool_view_runbook(args["service"], args["section"], self.scenario)
            self.state.last_tool_results["runbook"] = tool_result
        elif action_type == "create_incident":
            applied = not self.state.incident_created
            self.state.incident_created = True
            self.state.incident_severity = args["severity"]
        elif action_type == "assign_role":
            previous = self.state.roles_assigned.get(args["role"])
            applied = previous != args["assignee"]
            self.state.roles_assigned[args["role"]] = args["assignee"]
        elif action_type == "post_update":
            self.state.last_update_step = self.state.current_step
            self.state.updates_posted.append(deepcopy(args))
            self.state.message_feed.append(
                MessageRecord(
                    ts_step=self.state.current_step,
                    sender="incident-commander",
                    text=f"{args['audience']} update ({args['template_id']}): {args['fields']}",
                )
            )
        elif action_type == "request_help":
            tool_result = tool_request_help(args["team"], self.scenario)
        elif action_type == "apply_mitigation":
            mitigation_id = args["mitigation_id"]
            self.state.proposed_mitigations.append(mitigation_id)
        elif action_type == "toggle_feature_flag":
            self.state.feature_flags[args["flag"]] = args["enabled"]
            if args["flag"] == "new_pricing_path" and args["enabled"] is False:
                self._record_change_effect(
                    mitigation_id="disable_new_pricing_path",
                    change_type="toggle_feature_flag",
                    details={"flag": args["flag"], "enabled": args["enabled"]},
                )
        elif action_type == "apply_config_patch":
            patch_id = args["patch_id"]
            self.state.config_state[args["service"]] = f"{self.state.config_state[args['service']]}+{patch_id}"
            if args["service"] == "checkout-service" and patch_id == "fix_pricing_url_v42":
                self._record_change_effect(
                    mitigation_id="revert_pricing_url_config",
                    change_type="apply_config_patch",
                    details={"service": args["service"], "patch_id": patch_id},
                )
        elif action_type == "rollback_deploy":
            self.state.deploy_versions[args["service"]] = args["to_version"]
            if args["service"] == "checkout-service" and args["to_version"] == "v41":
                self._record_change_effect(
                    mitigation_id="rollback_checkout_v42_to_v41",
                    change_type="rollback_deploy",
                    details={
                        "service": args["service"],
                        "from_version": args["from_version"],
                        "to_version": args["to_version"],
                    },
                )
        elif action_type == "restart_service":
            self.state.service_restarts[args["service"]] += 1
            mitigation_id = self._map_service_change_to_mitigation(
                action_type="restart_service",
                service=args["service"],
            )
            if mitigation_id is not None:
                self._record_change_effect(
                    mitigation_id=mitigation_id,
                    change_type="restart_service",
                    details={"service": args["service"]},
                )
        elif action_type == "scale_service":
            self.state.service_replicas[args["service"]] = args["replicas"]
            mitigation_id = self._map_service_change_to_mitigation(
                action_type="scale_service",
                service=args["service"],
            )
            if mitigation_id is not None:
                self._record_change_effect(
                    mitigation_id=mitigation_id,
                    change_type="scale_service",
                    details={"service": args["service"], "replicas": args["replicas"]},
                )
        elif action_type == "run_health_check":
            healthy = self.state.service_health[args["service"]] == "healthy"
            tool_result = {
                "service": args["service"],
                "healthy": healthy,
                "checks": [
                    {"name": "readiness", "status": "ok" if healthy else "degraded"},
                    {"name": "latency", "status": "ok" if healthy else "degraded"},
                ],
            }
            self.state.last_tool_results["health"] = tool_result
        elif action_type == "wait":
            tool_result = None
        elif action_type == "confirm_metrics_normalized":
            metric_result = tool_get_metrics(
                service=args["service"],
                metric=args["metric"],
                window_steps=args["window_steps"],
                agg="mean",
                env_state=self.state,
            )
            actual = float(metric_result["agg"])
            confirmed = actual <= float(args["target"])
            tool_result = {
                "service": args["service"],
                "metric": args["metric"],
                "target": float(args["target"]),
                "actual": actual,
                "confirmed": confirmed,
            }
            if args["service"] == "checkout-service" and args["metric"] in self.state.confirmations:
                self.state.confirmations[args["metric"]] = confirmed
            self._refresh_resolved_state()
        elif action_type in {"declare_resolved", "declare_failed"}:
            tool_result = None

        return tool_result, applied

    def _map_service_change_to_mitigation(
        self,
        action_type: str,
        service: str,
    ) -> str | None:
        if action_type == "restart_service":
            if service == "checkout-service":
                return "restart_checkout_service"
            if service == "orders-db":
                return "restart_database"
            return None
        if action_type == "scale_service":
            if service == "checkout-service":
                return "scale_checkout_service"
            if service == "orders-db":
                return "scale_database"
            return None
        return None

    def _has_required_evidence(self) -> bool:
        assert self.state is not None
        return any(
            (
                self.state.evidence_flags["saw_config_diff"],
                self.state.evidence_flags["saw_key_log"],
                self.state.evidence_flags["saw_deploy"],
            )
        )

    def _record_change_effect(
        self,
        mitigation_id: str,
        change_type: str,
        details: dict[str, Any],
    ) -> None:
        assert self.state is not None
        self.state.last_executed_mitigation_id = mitigation_id
        self.state.executed_changes.append(
            {
                "step": self.state.current_step,
                "change_type": change_type,
                "mitigation_id": mitigation_id,
                "planned": mitigation_id in self.state.proposed_mitigations,
                "evidence_met": self._has_required_evidence(),
                "details": deepcopy(details),
            }
        )
        if mitigation_id not in self.state.mitigations_applied:
            self.state.mitigations_applied.append(mitigation_id)
        if mitigation_id in self.scenario.allowed_mitigations:
            self.state.causal_mitigation_id = mitigation_id
            self.state.causal_fix_step = self.state.current_step
            self.state.causal_change_planned = mitigation_id in self.state.proposed_mitigations
            self.state.causal_change_evidence_met = self._has_required_evidence()
            self.state.confirmations = {"error_rate": False, "p95_latency": False}
            self.state.resolved_state = False
