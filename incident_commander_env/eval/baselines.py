"""Baseline agents for the Stage 3 evaluation harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Any

from ..scenario import Scenario


def _missing_updates(observation: dict[str, Any], scenario: Scenario) -> list[tuple[str, str]]:
    posted = {
        (action["args"]["template_id"], action["args"]["audience"])
        for action in observation["recent_actions"]
        if action["type"] == "post_update"
    }
    missing = []
    for requirement in scenario.resolution_rubric.required_updates:
        key = (requirement.template_id, requirement.audience)
        if key not in posted:
            missing.append(key)
    return missing


@dataclass
class RandomAgent:
    """Random valid-ish baseline with deterministic throttling."""

    seed: int = 0
    rng: Random = field(init=False)
    scenario: Scenario | None = field(default=None, init=False)
    services: list[str] = field(default_factory=list, init=False)

    def reset(self, scenario: Scenario, seed: int) -> None:
        self.scenario = scenario
        self.rng = Random(seed)
        self.services = sorted(scenario.evidence.services.keys())

    def act(self, observation: dict[str, Any], last_info: dict[str, Any] | None) -> dict[str, Any]:
        assert self.scenario is not None
        primary_service = self.services[0]
        primary_metric = sorted(self.scenario.evidence.metric_profiles[primary_service].keys())[0]
        first_diff = self.scenario.evidence.config_diffs[0] if self.scenario.evidence.config_diffs else None
        first_trace = self.scenario.evidence.trace_samples[0] if self.scenario.evidence.trace_samples else None
        candidates: list[dict[str, Any]] = [
            {"type": "create_incident", "args": {"title": self.scenario.title, "severity": self.scenario.severity}},
            {"type": "list_services", "args": {}},
            {"type": "get_metrics", "args": {"service": primary_service, "metric": primary_metric, "window_steps": 1, "agg": "raw"}},
            {"type": "get_logs", "args": {"service": primary_service, "query": "", "window_steps": 4, "limit": 5, "page": 0}},
            {"type": "search_recent_deploys", "args": {"service": primary_service, "window_steps": 5}},
            {"type": "view_runbook", "args": {"service": primary_service, "section": "triage"}},
            {"type": "post_update", "args": {"audience": "internal", "template_id": "status", "fields": {"summary": "Investigating", "eta": "unknown"}}},
            {"type": "apply_mitigation", "args": {"mitigation_id": self.rng.choice(self.scenario.all_mitigations)}},
            {"type": "wait", "args": {"steps": 1}},
        ]
        if first_diff is not None:
            candidates.append(
                {
                    "type": "diff_config",
                    "args": {
                        "service": first_diff.service,
                        "from_version": first_diff.from_version,
                        "to_version": first_diff.to_version,
                    },
                }
            )
        if first_trace is not None:
            candidates.append(
                {
                    "type": "get_trace_sample",
                    "args": {"service": first_trace.service, "trace_id": first_trace.trace_id},
                }
            )
        for rule in self.scenario.mitigation_rules:
            candidates.append({"type": rule.action_type, "args": dict(rule.args_match)})
        for requirement in self.scenario.resolution_rubric.required_verification:
            candidates.append(
                {
                    "type": "confirm_metrics_normalized",
                    "args": {
                        "service": requirement.service,
                        "metric": requirement.metric,
                        "target": requirement.target,
                        "window_steps": requirement.window_steps,
                    },
                }
            )
        candidates.append(
            {
                "type": "declare_resolved",
                "args": {
                    "root_cause_id": self.scenario.ground_truth_root_cause_id,
                    "mitigation_id": self.scenario.allowed_mitigations[0],
                    "summary": "Tentative resolution",
                },
            }
        )
        return self.rng.choice(candidates)


@dataclass
class HeuristicAgent:
    """Deterministic evidence-driven baseline."""

    seed: int = 0
    scenario: Scenario | None = field(default=None, init=False)
    executed_rules: list[tuple[str, dict[str, Any]]] = field(default_factory=list, init=False)

    def reset(self, scenario: Scenario, seed: int) -> None:
        self.scenario = scenario
        self.executed_rules = []

    def act(self, observation: dict[str, Any], last_info: dict[str, Any] | None) -> dict[str, Any]:
        assert self.scenario is not None
        if not observation["incident"]["created"]:
            return {"type": "create_incident", "args": {"title": self.scenario.title, "severity": self.scenario.severity}}

        required_updates = _missing_updates(observation, self.scenario)
        if ("status", "internal") in required_updates:
            return {
                "type": "post_update",
                "args": {
                    "audience": "internal",
                    "template_id": "status",
                    "fields": {"summary": "Investigating incident impact.", "eta": "15 minutes"},
                },
            }

        if "metrics" not in observation["last_tool_results"]:
            first_service = sorted(self.scenario.evidence.metric_profiles.keys())[0]
            first_metric = sorted(self.scenario.evidence.metric_profiles[first_service].keys())[0]
            return {
                "type": "get_metrics",
                "args": {"service": first_service, "metric": first_metric, "window_steps": 1, "agg": "raw"},
            }
        if not observation["evidence_flags"]["saw_key_log"]:
            first_service = sorted(self.scenario.evidence.logs_by_service.keys())[0]
            query = self.scenario.evidence_markers["key_log_terms"][0].split()[0]
            return {
                "type": "get_logs",
                "args": {"service": first_service, "query": query, "window_steps": 5, "limit": 5, "page": 0},
            }
        if not observation["evidence_flags"]["saw_deploy"] and self.scenario.evidence.deploy_history:
            service = self.scenario.evidence_markers["deploy_service"]
            return {"type": "search_recent_deploys", "args": {"service": service, "window_steps": 6}}
        if not observation["evidence_flags"]["saw_config_diff"] and self.scenario.evidence.config_diffs:
            record = self.scenario.evidence.config_diffs[0]
            return {
                "type": "diff_config",
                "args": {"service": record.service, "from_version": record.from_version, "to_version": record.to_version},
            }
        if "saw_runbook" in self.scenario.resolution_rubric.required_evidence_flags and not observation["evidence_flags"]["saw_runbook"]:
            runbook_service = next(iter(self.scenario.evidence.runbook_snippets.keys()))
            return {"type": "view_runbook", "args": {"service": runbook_service, "section": "triage"}}

        if not observation["recent_actions"] or all(action["type"] != "apply_mitigation" for action in observation["recent_actions"]):
            return {"type": "apply_mitigation", "args": {"mitigation_id": self.scenario.allowed_mitigations[0]}}

        for rule in self.scenario.mitigation_rules:
            candidate = (rule.action_type, rule.args_match)
            if rule.causal and candidate not in self.executed_rules and rule.mitigation_id == self.scenario.allowed_mitigations[0]:
                self.executed_rules.append(candidate)
                return {"type": rule.action_type, "args": dict(rule.args_match)}

        if observation["step"] <= 8:
            return {"type": "wait", "args": {"steps": 1}}

        for requirement in self.scenario.resolution_rubric.required_verification:
            if requirement.metric not in observation["last_tool_results"].get("health", {}):
                return {
                    "type": "confirm_metrics_normalized",
                    "args": {
                        "service": requirement.service,
                        "metric": requirement.metric,
                        "target": requirement.target,
                        "window_steps": requirement.window_steps,
                    },
                }

        missing = _missing_updates(observation, self.scenario)
        if ("resolved", "internal") in missing:
            return {
                "type": "post_update",
                "args": {
                    "audience": "internal",
                    "template_id": "resolved",
                    "fields": {"summary": "Recovered", "customer_impact": "Resolved"},
                },
            }
        if ("status", "external") in missing:
            return {
                "type": "post_update",
                "args": {
                    "audience": "external",
                    "template_id": "status",
                    "fields": {"summary": "Mitigation in progress", "eta": "10 minutes"},
                },
            }

        return {
            "type": "declare_resolved",
            "args": {
                "root_cause_id": self.scenario.ground_truth_root_cause_id,
                "mitigation_id": self.scenario.allowed_mitigations[0],
                "summary": "Heuristic baseline resolution",
            },
        }
