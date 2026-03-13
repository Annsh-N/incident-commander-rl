"""Main Incident Commander environment."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from random import Random
from typing import Any

from .observation import build_observation
from .replay import ReplayBuffer
from .scenario import MessageDefinition, Scenario, load_scenario
from .tools import tool_get_logs, tool_get_metrics, tool_view_runbook
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
    limit: int
    page: int
    lines: list[str]
    next_page: int | None


@dataclass
class EnvState:
    """Environment state."""

    current_step: int
    scenario_id: str
    incident_status: str
    active_alerts: list[AlertState]
    message_feed: list[MessageRecord]
    metrics: dict[str, list[float]]
    logs: list[LogPageRecord]
    applied_actions: list[dict[str, Any]]
    scenario: Scenario
    last_mitigation_applied: str | None = None
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
        self.state = EnvState(
            current_step=0,
            scenario_id=scenario.id,
            incident_status="active",
            active_alerts=[],
            message_feed=[],
            metrics={
                metric: list(values)
                for metric, values in scenario.evidence.metrics_by_step.items()
            },
            logs=[],
            applied_actions=[],
            scenario=scenario,
            seed=seed,
        )
        self._done = False
        self._replay.reset()
        self._apply_timeline_events(0)
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
        }
        reward = -0.05
        action_copy = deepcopy(action)
        action_type = action_copy.get("type") if isinstance(action_copy, dict) else None

        is_valid, error = validate_action(action_copy, self.state)
        done = False

        if not is_valid:
            info["error"] = error
            info["debug"].append(error or "validation failed")
            reward -= 0.1
            if action_type == "declare_resolved":
                done = True
                self.state.incident_status = "failed"
                info["debug"].append("Resolution attempt failed before evaluation.")
                info["resolution"] = self._resolution_from_invalid_declare(action_copy)
        else:
            info["valid_action"] = True
            info["applied"] = True
            self.state.applied_actions.append(action_copy)
            info["tool_result"] = self._apply_action(action_copy, info)
            if action_type == "declare_resolved":
                done = True
                resolution, debug_lines = self._evaluate_resolution(action_copy)
                info["resolution"] = resolution
                info["debug"].extend(debug_lines)
                if resolution == "success":
                    reward += 1.0
                    self.state.incident_status = "resolved"
                else:
                    reward -= 1.0
                    self.state.incident_status = "failed"

        self.state.current_step += 1
        if not done:
            if self.state.current_step >= self.max_steps:
                done = True
                self.state.incident_status = "failed"
                info["debug"].append("Max steps reached before resolution.")
            else:
                self._apply_timeline_events(self.state.current_step)

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
        if self.state is None:
            return
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

    def _apply_action(
        self, action: dict[str, Any], info: dict[str, Any]
    ) -> dict[str, Any] | str | None:
        assert self.state is not None
        action_type = action["type"]
        args = action["args"]

        if action_type == "ack_alert":
            for alert in self.state.active_alerts:
                if alert.id == args["alert_id"]:
                    alert.acknowledged = True
                    break
            return {"acknowledged_alert_id": args["alert_id"]}

        if action_type == "get_metrics":
            return tool_get_metrics(
                metric=args["metric"],
                window=args["window"],
                current_step=self.state.current_step,
                scenario=self.scenario,
            )

        if action_type == "get_logs":
            result = tool_get_logs(
                service=args["service"],
                query=args["query"],
                limit=args["limit"],
                page=args["page"],
                scenario=self.scenario,
            )
            self.state.logs.append(
                LogPageRecord(
                    step=self.state.current_step,
                    service=args["service"],
                    query=args["query"],
                    limit=args["limit"],
                    page=args["page"],
                    lines=list(result["lines"]),
                    next_page=result["next_page"],
                )
            )
            return result

        if action_type == "view_runbook":
            return tool_view_runbook(args["service"], self.scenario)

        if action_type == "apply_mitigation":
            self.state.last_mitigation_applied = args["mitigation_id"]
            return {"mitigation_applied": args["mitigation_id"]}

        if action_type == "post_update":
            audience = args["audience"]
            template_id = args["template_id"]
            self.state.message_feed.append(
                MessageRecord(
                    ts_step=self.state.current_step,
                    sender="incident-commander",
                    text=f"Posted {audience} update using template {template_id}.",
                )
            )
            return {"audience": audience, "template_id": template_id}

        if action_type == "declare_resolved":
            return {
                "root_cause_id": args["root_cause_id"],
                "mitigation_id": args["mitigation_id"],
            }

        info["applied"] = False
        return None

    def _evaluate_resolution(
        self, action: dict[str, Any]
    ) -> tuple[str, list[str]]:
        assert self.state is not None
        args = action["args"]
        debug_lines: list[str] = []
        root_cause_matches = (
            args["root_cause_id"] == self.scenario.ground_truth_root_cause_id
        )
        mitigation_allowed = args["mitigation_id"] in set(self.scenario.allowed_mitigations)

        if root_cause_matches and mitigation_allowed:
            return "success", ["Resolution accepted."]

        if not root_cause_matches:
            debug_lines.append(
                "Wrong root cause. Expected "
                f"{self.scenario.ground_truth_root_cause_id}, received {args['root_cause_id']}."
            )
        if not mitigation_allowed:
            debug_lines.append(
                "Wrong mitigation. Allowed mitigations are "
                f"{self.scenario.allowed_mitigations}, received {args['mitigation_id']}."
            )

        resolution = "wrong_root_cause" if not root_cause_matches else "wrong_mitigation"
        return resolution, debug_lines

    def _resolution_from_invalid_declare(self, action: dict[str, Any]) -> str | None:
        if not isinstance(action, dict):
            return None
        args = action.get("args")
        if not isinstance(args, dict):
            return None
        mitigation_id = args.get("mitigation_id")
        if isinstance(mitigation_id, str):
            known_ids = set(self.scenario.allowed_mitigations) | set(
                self.scenario.forbidden_mitigations
            )
            if mitigation_id not in known_ids:
                return "wrong_mitigation"
        root_cause_id = args.get("root_cause_id")
        if isinstance(root_cause_id, str):
            if root_cause_id != self.scenario.ground_truth_root_cause_id:
                return "wrong_root_cause"
        return None
