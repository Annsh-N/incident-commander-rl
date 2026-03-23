"""Baseline agents for the Stage 3 evaluation harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Any


CONCRETE_ACTION_TYPES = {
    "toggle_feature_flag",
    "apply_config_patch",
    "rollback_deploy",
    "restart_service",
    "scale_service",
}

CATEGORY_KEYWORDS = {
    "deploy": ["pricing", "url", "deploy", "checkout"],
    "db": ["pool", "connection", "db", "checkout"],
    "queue": ["queue", "worker", "consumer", "concurrency"],
    "dependency": ["dependency", "fallback", "catalog", "degrade"],
    "memory": ["memory", "oom", "leak", "rollback"],
    "dns": ["dns", "resolver", "resolve", "tax"],
    "retry": ["retry", "herd", "rate", "gateway"],
    "security": ["permission", "iam", "policy", "access"],
}

ROOT_CAUSE_HINTS = {
    "deploy": ["pricing_url", "pricing", "deploy"],
    "db": ["pool", "connection"],
    "queue": ["queue", "concurrency", "worker"],
    "dependency": ["fallback", "dependency", "outage"],
    "memory": ["memory", "leak", "oom"],
    "dns": ["dns", "resolver", "resolution"],
    "retry": ["retry", "herd", "backoff"],
    "security": ["permission", "iam", "policy", "access"],
}

CATEGORY_TARGET_METRICS = {
    "deploy": ["error_rate", "p95_latency"],
    "db": ["error_rate", "db_conn"],
    "queue": ["queue_depth", "p95_latency"],
    "dependency": ["error_rate", "dependency_503_rate"],
    "memory": ["memory_usage", "error_rate"],
    "dns": ["error_rate", "p95_latency"],
    "retry": ["retry_rate", "p95_latency"],
    "security": ["access_denied_rate", "error_rate"],
}


def _contains_any(text: str, tokens: list[str]) -> bool:
    lowered = text.casefold()
    return any(token.casefold() in lowered for token in tokens)


def _serialize_signature(action_type: str, args: dict[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return action_type, tuple(sorted((key, repr(value)) for key, value in args.items()))


def _pick_by_keywords(values: list[str], keywords: list[str]) -> str | None:
    for value in values:
        if _contains_any(value, keywords):
            return value
    return values[0] if values else None


@dataclass
class RandomAgent:
    """Random valid-ish baseline with deterministic throttling."""

    seed: int = 0
    rng: Random = field(init=False)
    scenario: Any | None = field(default=None, init=False)
    services: list[str] = field(default_factory=list, init=False)

    def reset(self, scenario: Any, seed: int) -> None:
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
            {
                "type": "create_incident",
                "args": {"title": self.scenario.title, "severity": self.scenario.severity},
            },
            {"type": "list_services", "args": {}},
            {
                "type": "get_metrics",
                "args": {
                    "service": primary_service,
                    "metric": primary_metric,
                    "window_steps": 1,
                    "agg": "raw",
                },
            },
            {
                "type": "get_logs",
                "args": {
                    "service": primary_service,
                    "query": "",
                    "window_steps": 4,
                    "limit": 5,
                    "page": 0,
                },
            },
            {
                "type": "search_recent_deploys",
                "args": {"service": primary_service, "window_steps": 5},
            },
            {"type": "view_runbook", "args": {"service": primary_service, "section": "triage"}},
            {
                "type": "post_update",
                "args": {
                    "audience": "internal",
                    "template_id": "status",
                    "fields": {"summary": "Investigating", "eta": "unknown"},
                },
            },
            {
                "type": "apply_mitigation",
                "args": {"mitigation_id": self.rng.choice(self.scenario.all_mitigations)},
            },
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
    """Deterministic finite-state baseline using only public observations and tool outputs."""

    category: str | None = field(default=None, init=False)
    posted_updates: set[tuple[str, str]] = field(default_factory=set, init=False)
    queried_metrics: set[tuple[str, str]] = field(default_factory=set, init=False)
    queried_logs: set[str] = field(default_factory=set, init=False)
    executed_signatures: set[tuple[str, tuple[tuple[str, str], ...]]] = field(default_factory=set, init=False)
    verification_confirmed: set[tuple[str, str]] = field(default_factory=set, init=False)
    seen_deploy: bool = field(default=False, init=False)
    seen_diff: bool = field(default=False, init=False)
    seen_trace: bool = field(default=False, init=False)
    seen_runbook: bool = field(default=False, init=False)
    observed_log_text: list[str] = field(default_factory=list, init=False)
    observed_diff_keys: list[str] = field(default_factory=list, init=False)
    observed_trace_errors: list[str] = field(default_factory=list, init=False)
    chosen_mitigation_id: str | None = field(default=None, init=False)
    chosen_root_cause_id: str | None = field(default=None, init=False)
    plan_actions: list[dict[str, Any]] = field(default_factory=list, init=False)
    wait_steps_taken: int = field(default=0, init=False)

    def reset(self, scenario: Any, seed: int) -> None:  # noqa: ARG002 - scenario kept out of policy logic
        self.category = None
        self.posted_updates.clear()
        self.queried_metrics.clear()
        self.queried_logs.clear()
        self.executed_signatures.clear()
        self.verification_confirmed.clear()
        self.seen_deploy = False
        self.seen_diff = False
        self.seen_trace = False
        self.seen_runbook = False
        self.observed_log_text.clear()
        self.observed_diff_keys.clear()
        self.observed_trace_errors.clear()
        self.chosen_mitigation_id = None
        self.chosen_root_cause_id = None
        self.plan_actions.clear()
        self.wait_steps_taken = 0

    def _observe(self, observation: dict[str, Any], last_info: dict[str, Any] | None) -> None:
        self.category = observation["incident"].get("category", "generic")
        last_action = observation["recent_actions"][-1] if observation["recent_actions"] else None
        if last_action is None:
            return

        if last_action["type"] == "post_update":
            self.posted_updates.add(
                (last_action["args"]["template_id"], last_action["args"]["audience"])
            )
        signature = _serialize_signature(last_action["type"], last_action["args"])
        self.executed_signatures.add(signature)
        if last_action["type"] == "confirm_metrics_normalized":
            self.verification_confirmed.add(
                (last_action["args"]["service"], last_action["args"]["metric"])
            )
        if last_action["type"] == "wait":
            self.wait_steps_taken += int(last_action["args"]["steps"])

        if not last_info or last_info.get("tool_result") is None:
            return

        action_type = last_action["type"]
        tool_result = last_info["tool_result"]
        if action_type == "search_recent_deploys":
            self.seen_deploy = bool(tool_result.get("events"))
        elif action_type == "diff_config":
            self.seen_diff = bool(tool_result.get("diff"))
            self.observed_diff_keys.extend(item["key"] for item in tool_result.get("diff", []))
        elif action_type == "get_trace_sample":
            self.seen_trace = bool(tool_result.get("trace_id"))
            if tool_result.get("error"):
                self.observed_trace_errors.append(tool_result["error"])
        elif action_type == "view_runbook":
            self.seen_runbook = True
        elif action_type == "get_logs":
            self.observed_log_text.extend(
                line["message"] for line in tool_result.get("lines", [])
            )
        elif action_type == "get_metrics":
            self.queried_metrics.add((tool_result["service"], tool_result["metric"]))
        elif action_type == "confirm_metrics_normalized" and tool_result.get("confirmed"):
            self.verification_confirmed.add((tool_result["service"], tool_result["metric"]))

    def _missing_updates(self, observation: dict[str, Any]) -> list[tuple[str, str]]:
        requirements = observation["resolution_hints"]["required_updates"]
        return [
            (item["template_id"], item["audience"])
            for item in requirements
            if (item["template_id"], item["audience"]) not in self.posted_updates
        ]

    def _query_sequence(self, observation: dict[str, Any]) -> list[str]:
        hints = list(observation["action_catalog"]["query_hints"])
        alert_text = " ".join(alert["signal"] for alert in observation["alerts"])
        message_text = " ".join(message["text"] for message in observation["messages"])
        combined = f"{alert_text} {message_text}".casefold()
        if "timeout" in combined and "DNS" not in hints:
            hints.extend(["timeout", "DNS"])
        if "permission" in combined and "AccessDenied" not in hints:
            hints.extend(["AccessDenied"])
        if "connection" in combined and "too many connections" not in hints:
            hints.extend(["too many connections"])
        ordered: list[str] = []
        for hint in hints:
            if hint not in ordered:
                ordered.append(hint)
        return ordered

    def _choose_root_cause(self, observation: dict[str, Any]) -> str:
        category = observation["incident"].get("category", "generic")
        candidates = observation["resolution_hints"]["root_cause_candidates"]
        evidence_text = " ".join(
            [
                *self.observed_log_text,
                *self.observed_diff_keys,
                *self.observed_trace_errors,
            ]
        ).casefold()
        keywords = ROOT_CAUSE_HINTS.get(category, CATEGORY_KEYWORDS.get(category, []))
        scored_candidates = []
        for candidate in candidates:
            candidate_text = candidate.casefold()
            score = 0
            for keyword in keywords:
                if keyword.casefold() in candidate_text:
                    score += 3
                if evidence_text and keyword.casefold() in candidate_text and keyword.casefold() in evidence_text:
                    score += 5
            if evidence_text:
                for token in candidate_text.replace("-", "_").split("_"):
                    if token and token in evidence_text:
                        score += 1
            scored_candidates.append((score, candidate))
        scored_candidates.sort(key=lambda item: (-item[0], item[1]))
        return scored_candidates[0][1]

    def _choose_plan(self, observation: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        category = observation["incident"].get("category", "generic")
        allowed = list(observation["allowed_mitigations"])
        catalog = observation["action_catalog"]["mitigation_actions"]
        category_keywords = CATEGORY_KEYWORDS.get(category, [])

        preferred = []
        for mitigation_id in allowed:
            score = 0
            if _contains_any(mitigation_id, category_keywords):
                score += 3
            if category == "deploy" and _contains_any(mitigation_id, ["pricing", "rollback"]):
                score += 2
            if category == "db" and _contains_any(mitigation_id, ["pool", "scale"]):
                score += 2
            if category == "queue" and _contains_any(mitigation_id, ["consumer", "worker", "queue"]):
                score += 2
            if category == "dependency" and _contains_any(mitigation_id, ["fallback", "degrade"]):
                score += 2
            if category == "memory" and _contains_any(mitigation_id, ["rollback", "restart"]):
                score += 1
            if category == "dns" and _contains_any(mitigation_id, ["dns", "resolver", "rollback"]):
                score += 2
            if category == "retry" and _contains_any(mitigation_id, ["retry", "rate"]):
                score += 2
            if category == "security" and _contains_any(mitigation_id, ["permission", "iam", "policy"]):
                score += 2
            preferred.append((score, mitigation_id))
        preferred.sort(key=lambda item: (-item[0], item[1]))
        mitigation_id = preferred[0][1]
        plan_actions = [
            {"type": item["action_type"], "args": dict(item["args"])}
            for item in catalog
            if item["mitigation_id"] == mitigation_id and not item["forbidden"]
        ]
        plan_actions.sort(key=lambda item: (item["type"], str(item["args"])))
        return mitigation_id, plan_actions

    def _next_metric_query(self, observation: dict[str, Any]) -> dict[str, Any] | None:
        verification_targets = observation["resolution_hints"]["verification_targets"]
        for requirement in verification_targets:
            service = requirement["service"]
            metric = requirement["metric"]
            if (service, metric) not in self.queried_metrics:
                return {
                    "type": "get_metrics",
                    "args": {
                        "service": service,
                        "metric": metric,
                        "window_steps": 1,
                        "agg": "raw",
                    },
                }
        primary_service = observation["incident"]["primary_service"]
        metrics = CATEGORY_TARGET_METRICS.get(self.category or "generic", ["error_rate", "p95_latency"])
        for metric in metrics:
            if metric in observation["metrics_snapshot"] and (primary_service, metric) not in self.queried_metrics:
                return {
                    "type": "get_metrics",
                    "args": {
                        "service": primary_service,
                        "metric": metric,
                        "window_steps": 1,
                        "agg": "raw",
                    },
                }
        return None

    def _next_investigation(self, observation: dict[str, Any]) -> dict[str, Any] | None:
        metric_action = self._next_metric_query(observation)
        if metric_action is not None:
            return metric_action

        if not observation["evidence_flags"]["saw_key_log"]:
            for query in self._query_sequence(observation):
                if query in self.queried_logs:
                    continue
                self.queried_logs.add(query)
                return {
                    "type": "get_logs",
                    "args": {
                        "service": observation["action_catalog"]["log_service"],
                        "query": query,
                        "window_steps": 6,
                        "limit": 10,
                        "page": 0,
                    },
                }

        category = self.category or "generic"
        if category in {"deploy", "db", "memory", "dns"} and not self.seen_deploy:
            rollback_options = observation["action_catalog"]["rollback_options"]
            if rollback_options:
                return {
                    "type": "search_recent_deploys",
                    "args": {"service": rollback_options[0]["service"], "window_steps": 6},
                }

        if category in {"deploy", "db", "queue", "dns", "retry", "security"} and not self.seen_diff:
            diff_options = observation["action_catalog"]["config_diff_options"]
            if diff_options:
                option = diff_options[0]
                return {"type": "diff_config", "args": dict(option)}

        if category in {"dependency", "dns"} and not self.seen_trace:
            traces = observation["action_catalog"]["trace_samples"]
            if traces:
                return {"type": "get_trace_sample", "args": dict(traces[0])}

        if category == "security" and not self.seen_runbook:
            runbook_services = observation["action_catalog"]["runbook_services"]
            if runbook_services:
                return {
                    "type": "view_runbook",
                    "args": {"service": runbook_services[0], "section": "mitigation"},
                }
        return None

    def _next_missing_update(self, observation: dict[str, Any]) -> dict[str, Any] | None:
        for template_id, audience in self._missing_updates(observation):
            fields: dict[str, Any]
            if template_id == "status":
                fields = {"summary": "Mitigation in progress", "eta": "10 minutes"}
            elif template_id == "initial":
                fields = {"summary": "Investigating incident", "impact": "Customer traffic degraded"}
            elif template_id == "mitigation":
                fields = {"mitigation": self.chosen_mitigation_id or "pending", "owner": "heuristic-agent"}
            else:
                fields = {"summary": "Recovered", "customer_impact": "Resolved"}
            return {
                "type": "post_update",
                "args": {"audience": audience, "template_id": template_id, "fields": fields},
            }
        return None

    def act(self, observation: dict[str, Any], last_info: dict[str, Any] | None) -> dict[str, Any]:
        self._observe(observation, last_info)

        if not observation["incident"]["created"]:
            title = f"{observation['incident']['primary_service']} incident"
            return {
                "type": "create_incident",
                "args": {"title": title, "severity": observation["severity"]},
            }

        update_action = self._next_missing_update(observation)
        if update_action is not None and ("status", "internal") not in self.posted_updates:
            return update_action

        investigation_action = self._next_investigation(observation)
        if investigation_action is not None:
            return investigation_action

        if self.chosen_mitigation_id is None:
            self.chosen_mitigation_id, self.plan_actions = self._choose_plan(observation)
            self.chosen_root_cause_id = self._choose_root_cause(observation)

        recent_types = {action["type"] for action in observation["recent_actions"]}
        if "apply_mitigation" not in recent_types and _serialize_signature(
            "apply_mitigation", {"mitigation_id": self.chosen_mitigation_id}
        ) not in self.executed_signatures:
            return {
                "type": "apply_mitigation",
                "args": {"mitigation_id": self.chosen_mitigation_id},
            }

        for action in self.plan_actions:
            signature = _serialize_signature(action["type"], action["args"])
            if signature not in self.executed_signatures:
                return action

        if self.wait_steps_taken < 2:
            return {"type": "wait", "args": {"steps": 1}}

        for requirement in observation["resolution_hints"]["verification_targets"]:
            key = (requirement["service"], requirement["metric"])
            if key not in self.verification_confirmed:
                return {
                    "type": "confirm_metrics_normalized",
                    "args": dict(requirement),
                }

        update_action = self._next_missing_update(observation)
        if update_action is not None:
            return update_action

        assert self.chosen_root_cause_id is not None
        assert self.chosen_mitigation_id is not None
        return {
            "type": "declare_resolved",
            "args": {
                "root_cause_id": self.chosen_root_cause_id,
                "mitigation_id": self.chosen_mitigation_id,
                "summary": "Heuristic baseline resolution",
            },
        }
