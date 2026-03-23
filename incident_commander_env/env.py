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
    proposed_mitigations: list[str] = field(default_factory=list)
    executed_changes: list[dict[str, Any]] = field(default_factory=list)
    executed_mitigation_counts: dict[str, int] = field(default_factory=dict)
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
    verification_results: dict[tuple[str, str], bool] = field(default_factory=dict)
    evidence_flags: dict[str, bool] = field(default_factory=dict)
    last_tool_results: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    action_signature_counts: dict[str, int] = field(default_factory=dict)
    investigation_categories_used: set[str] = field(default_factory=set)
    tool_rewarded: set[str] = field(default_factory=set)
    rewarded_updates: set[tuple[str, str]] = field(default_factory=set)
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
            service_name: {
                metric: []
                for metric in scenario.evidence.metric_profiles.get(service_name, {}).keys()
            }
            for service_name in scenario.evidence.services.keys()
        }
        verification_results = {
            (requirement.service, requirement.metric): False
            for requirement in scenario.resolution_rubric.required_verification
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
                service.name: service.initial_replicas
                for service in scenario.evidence.services.values()
            },
            service_restarts={
                service.name: 0 for service in scenario.evidence.services.values()
            },
            verification_results=verification_results,
            evidence_flags={
                "saw_deploy": False,
                "saw_config_diff": False,
                "saw_key_log": False,
                "saw_timeout_trace": False,
                "saw_runbook": False,
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
            rewards_claimed={"incident_created_early": False},
            seed=seed,
        )
        self._done = False
        self._replay.reset()
        self._replay.set_context(scenario.id, seed)
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
            "failure_reasons": [],
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
                info["failure_reasons"] = ["invalid_termination_action"]
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
        """Return the replay events."""

        return self._replay.as_list()

    def save_replay(self, path: str) -> None:
        """Persist the replay to disk as JSONL."""

        self._replay.save_replay(path)

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
        profile = self.scenario.evidence.metric_profiles[service][metric]
        degraded_value = float(profile.degraded[min(step, len(profile.degraded) - 1)])

        if self.state.causal_fix_step is not None and step > self.state.causal_fix_step:
            offset = step - self.state.causal_fix_step - 1
            return float(profile.stabilized[min(offset, len(profile.stabilized) - 1)])

        if self.state.executed_changes:
            latest = self.state.executed_changes[-1]
            latest_service = latest["details"].get("service")
            latest_type = latest["change_type"]
            if latest_service == service and latest_type == "restart_service":
                if metric == "p95_latency":
                    return max(0.0, degraded_value - 70.0)
                if metric == "memory_usage":
                    return max(0.0, degraded_value - 8.0)
                if metric == "cpu":
                    return max(0.0, degraded_value - 3.0)
            if latest_service == service and latest_type == "scale_service":
                if metric == "p95_latency":
                    return max(0.0, degraded_value - 110.0)
                if metric == "error_rate":
                    return max(0.0, degraded_value - 0.5)
                if metric == "queue_depth":
                    return max(0.0, degraded_value - 60.0)
                if metric == "retry_rate":
                    return max(0.0, degraded_value - 10.0)
                if metric == "db_conn":
                    return max(0.0, degraded_value - 5.0)
        return degraded_value

    def _refresh_service_health(self) -> None:
        assert self.state is not None
        health: dict[str, str] = {}
        for service in self.scenario.evidence.services.keys():
            relevant_checks = [
                requirement
                for requirement in self.scenario.resolution_rubric.required_verification
                if requirement.service == service
            ]
            if relevant_checks:
                healthy = True
                for requirement in relevant_checks:
                    current_value = self.state.metrics[service][requirement.metric][-1]
                    if current_value > requirement.target:
                        healthy = False
                        break
                health[service] = "healthy" if healthy else "degraded"
            else:
                metric_map = self.state.metrics[service]
                if "error_rate" in metric_map and metric_map["error_rate"][-1] > 2.5:
                    health[service] = "degraded"
                else:
                    health[service] = "healthy"
        self.state.service_health = health

    def _required_evidence_available(self) -> bool:
        assert self.state is not None
        required = self.scenario.resolution_rubric.required_evidence_flags
        return all(self.state.evidence_flags.get(flag, False) for flag in required)

    def _refresh_resolved_state(self) -> None:
        assert self.state is not None
        waited_after_fix = (
            self.state.causal_fix_step is not None and self.state.current_step > self.state.causal_fix_step
        )
        verifications_complete = all(
            self.state.verification_results.get((requirement.service, requirement.metric), False)
            for requirement in self.scenario.resolution_rubric.required_verification
        )
        enough_investigation = (
            len(self.state.investigation_categories_used)
            >= self.scenario.resolution_rubric.min_investigation_categories
        )
        self.state.resolved_state = bool(
            self.state.causal_mitigation_id
            and self.state.causal_change_planned
            and self.state.causal_change_evidence_met
            and enough_investigation
            and waited_after_fix
            and verifications_complete
        )

    def _rule_matches(self, action_type: str, args: dict[str, Any]) -> list[Any]:
        matches = []
        for rule in self.scenario.mitigation_rules:
            if rule.action_type != action_type:
                continue
            if all(args.get(key) == value for key, value in rule.args_match.items()):
                matches.append(rule)
        return matches

    def _record_matching_mitigations(self, action_type: str, args: dict[str, Any]) -> None:
        assert self.state is not None
        matches = self._rule_matches(action_type, args)
        for rule in matches:
            self.state.last_executed_mitigation_id = rule.mitigation_id
            self.state.executed_changes.append(
                {
                    "step": self.state.current_step,
                    "change_type": action_type,
                    "mitigation_id": rule.mitigation_id,
                    "planned": rule.mitigation_id in self.state.proposed_mitigations,
                    "evidence_met": self._required_evidence_available(),
                    "details": deepcopy(args),
                }
            )
            self.state.executed_mitigation_counts[rule.mitigation_id] = (
                self.state.executed_mitigation_counts.get(rule.mitigation_id, 0) + 1
            )
            if rule.forbidden:
                self.state.unsafe_attempt = True

        for causal_group in self.scenario.causal_action_sets:
            required_counts: dict[str, int] = {}
            for mitigation_id in causal_group:
                required_counts[mitigation_id] = required_counts.get(mitigation_id, 0) + 1
            satisfied = all(
                self.state.executed_mitigation_counts.get(mitigation_id, 0) >= count
                for mitigation_id, count in required_counts.items()
            )
            if satisfied:
                primary_id = causal_group[0]
                self.state.causal_mitigation_id = primary_id
                self.state.causal_fix_step = self.state.current_step
                self.state.causal_change_planned = primary_id in self.state.proposed_mitigations
                self.state.causal_change_evidence_met = self._required_evidence_available()
                for requirement in self.scenario.resolution_rubric.required_verification:
                    self.state.verification_results[(requirement.service, requirement.metric)] = False
                self.state.resolved_state = False
                break

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
            self.state.proposed_mitigations.append(args["mitigation_id"])
        elif action_type == "toggle_feature_flag":
            self.state.feature_flags[args["flag"]] = args["enabled"]
            self._record_matching_mitigations(action_type, args)
        elif action_type == "apply_config_patch":
            patch_id = args["patch_id"]
            self.state.config_state[args["service"]] = f"{self.state.config_state[args['service']]}+{patch_id}"
            self._record_matching_mitigations(action_type, args)
        elif action_type == "rollback_deploy":
            self.state.deploy_versions[args["service"]] = args["to_version"]
            self._record_matching_mitigations(action_type, args)
        elif action_type == "restart_service":
            self.state.service_restarts[args["service"]] += 1
            self._record_matching_mitigations(action_type, args)
        elif action_type == "scale_service":
            self.state.service_replicas[args["service"]] = args["replicas"]
            self._record_matching_mitigations(action_type, args)
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
            for requirement in self.scenario.resolution_rubric.required_verification:
                if requirement.service == args["service"] and requirement.metric == args["metric"]:
                    self.state.verification_results[(requirement.service, requirement.metric)] = (
                        actual <= requirement.target
                    )
            self._refresh_resolved_state()
        elif action_type in {"declare_resolved", "declare_failed"}:
            tool_result = None

        return tool_result, applied
