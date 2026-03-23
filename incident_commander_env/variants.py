"""Deterministic scenario variant generation."""

from __future__ import annotations

import copy
import hashlib
from random import Random
from typing import Any

from .scenario import Scenario, load_base_scenarios, scenario_to_payload, _scenario_from_payload


def _stable_seed(*parts: str | int) -> int:
    joined = "::".join(str(part) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _replace_text(text: str, replacements: dict[str, str]) -> str:
    updated = text
    for source, target in replacements.items():
        updated = updated.replace(source, target)
    return updated


def _apply_noise_injection(payload: dict[str, Any], rng: Random) -> str:
    for service, entries in payload["evidence"]["logs"].items():
        for index in range(rng.randint(1, 2)):
            entries.append(
                {
                    "step": rng.randint(0, 3),
                    "service": service,
                    "level": "INFO",
                    "message": f"background job heartbeat ok variant_noise_{index}",
                }
            )
    if payload["timeline_events"]:
        payload["timeline_events"][0].setdefault("alerts", []).append(
            {
                "id": f"distractor-alert-{rng.randint(10, 99)}",
                "service": payload["services"][-1]["name"],
                "signal": "cpu > historical_baseline",
                "active": True,
            }
        )
    return "noise_injection"


def _apply_evidence_shuffle(payload: dict[str, Any], rng: Random) -> str:
    markers = payload["evidence_markers"]["key_log_terms"]
    for service, entries in payload["evidence"]["logs"].items():
        matching = [entry for entry in entries if any(term in entry["message"] for term in markers)]
        if not matching:
            continue
        key_entry = matching[0]
        entries.remove(key_entry)
        insert_at = min(len(entries), rng.randint(max(1, len(entries) // 2), len(entries)))
        entries.insert(insert_at, key_entry)
    return "evidence_shuffle"


def _apply_metric_jitter(payload: dict[str, Any], rng: Random) -> str:
    rubric_targets = {
        (item["service"], item["metric"]): float(item["target"])
        for item in payload["resolution_rubric"]["required_verification"]
    }
    for service, metrics in payload["evidence"]["metrics"].items():
        for metric_name, metric_payload in metrics.items():
            degraded = []
            stabilized = []
            target = rubric_targets.get((service, metric_name))
            for value in metric_payload["degraded"]:
                jitter = 1.0 + rng.uniform(-0.04, 0.04)
                new_value = round(float(value) * jitter, 3)
                if target is not None:
                    new_value = max(new_value, target * 1.15)
                degraded.append(new_value)
            for value in metric_payload["stabilized"]:
                jitter = 1.0 + rng.uniform(-0.03, 0.03)
                new_value = round(float(value) * jitter, 3)
                if target is not None:
                    new_value = min(new_value, target * 0.9)
                stabilized.append(new_value)
            metric_payload["degraded"] = degraded
            metric_payload["stabilized"] = stabilized
    return "metric_jitter"


def _apply_timeline_shift(payload: dict[str, Any], rng: Random) -> str:
    for event in payload["timeline_events"]:
        if event["step"] == 0:
            continue
        event["step"] = max(1, min(7, event["step"] + rng.choice([-1, 0, 1])))
        for message in event.get("messages", []):
            message["ts_step"] = event["step"]
    payload["timeline_events"].sort(key=lambda item: item["step"])
    return "timeline_shift"


def _apply_consistent_rename(payload: dict[str, Any], rng: Random) -> str:
    service_map: dict[str, str] = {}
    for service in payload["services"]:
        suffix = rng.choice(["edge", "mesh", "core", "svc"])
        service_map[service["name"]] = f"{service['name'].split('-')[0]}-{suffix}"

    flag_map = {flag: f"{flag}_variant" for flag in list(payload["feature_flags"].keys())}
    config_keys = set(payload["evidence_markers"].get("config_keys", []))
    config_map = {key: f"{key}_ALT" for key in config_keys}
    replacements = {}
    replacements.update(service_map)
    replacements.update(flag_map)
    replacements.update(config_map)

    for service in payload["services"]:
        old_name = service["name"]
        service["name"] = service_map[old_name]
        service["dependencies"] = [service_map.get(dep, dep) for dep in service["dependencies"]]
        service["description"] = _replace_text(service["description"], replacements)
    for event in payload["timeline_events"]:
        for alert in event.get("alerts", []):
            alert["service"] = service_map.get(alert["service"], alert["service"])
            alert["signal"] = _replace_text(alert["signal"], replacements)
        for message in event.get("messages", []):
            message["text"] = _replace_text(message["text"], replacements)
    evidence = payload["evidence"]
    evidence["metrics"] = {
        service_map.get(service, service): value for service, value in evidence["metrics"].items()
    }
    evidence["logs"] = {
        service_map.get(service, service): [
            {
                **entry,
                "service": service_map.get(entry["service"], entry["service"]),
                "message": _replace_text(entry["message"], replacements),
            }
            for entry in entries
        ]
        for service, entries in evidence["logs"].items()
    }
    for deploy in evidence["deploy_history"]:
        deploy["service"] = service_map.get(deploy["service"], deploy["service"])
    for record in evidence["config_diffs"]:
        record["service"] = service_map.get(record["service"], record["service"])
        for diff_entry in record["diff"]:
            diff_entry["key"] = config_map.get(diff_entry["key"], diff_entry["key"])
            diff_entry["from"] = _replace_text(diff_entry["from"], replacements)
            diff_entry["to"] = _replace_text(diff_entry["to"], replacements)
    for sample in evidence["trace_samples"]:
        sample["service"] = service_map.get(sample["service"], sample["service"])
        sample["error"] = _replace_text(sample["error"], replacements) if sample.get("error") else None
        for span in sample["spans"]:
            span["service"] = service_map.get(span["service"], span["service"])
            span["operation"] = _replace_text(span["operation"], replacements)
    evidence["runbook_snippets"] = {
        service_map.get(service, service): {
            section: [_replace_text(line, replacements) for line in lines]
            for section, lines in sections.items()
        }
        for service, sections in evidence["runbook_snippets"].items()
    }
    evidence["help_responses"] = {
        team: _replace_text(message, replacements)
        for team, message in evidence["help_responses"].items()
    }
    payload["patch_ids"] = {
        service_map.get(service, service): value for service, value in payload["patch_ids"].items()
    }
    payload["feature_flags"] = {
        flag_map.get(flag, flag): value for flag, value in payload["feature_flags"].items()
    }
    payload["deploy_versions"] = {
        service_map.get(service, service): value for service, value in payload["deploy_versions"].items()
    }
    payload["config_versions"] = {
        service_map.get(service, service): value for service, value in payload["config_versions"].items()
    }
    for rule in payload["mitigation_rules"]:
        if "service" in rule["args_match"]:
            rule["args_match"]["service"] = service_map.get(
                rule["args_match"]["service"], rule["args_match"]["service"]
            )
        if "flag" in rule["args_match"]:
            rule["args_match"]["flag"] = flag_map.get(rule["args_match"]["flag"], rule["args_match"]["flag"])
    for requirement in payload["resolution_rubric"]["required_verification"]:
        requirement["service"] = service_map.get(requirement["service"], requirement["service"])
    payload["evidence_markers"]["deploy_service"] = service_map.get(
        payload["evidence_markers"]["deploy_service"],
        payload["evidence_markers"]["deploy_service"],
    )
    payload["evidence_markers"]["config_keys"] = [
        config_map.get(key, key) for key in payload["evidence_markers"].get("config_keys", [])
    ]
    payload["evidence_markers"]["key_log_terms"] = [
        _replace_text(term, replacements) for term in payload["evidence_markers"].get("key_log_terms", [])
    ]
    return "consistent_rename"


def _apply_false_lead_trace(payload: dict[str, Any], rng: Random) -> str:
    services = [service["name"] for service in payload["services"]]
    if len(services) < 2:
        return "false_lead_trace"
    payload["evidence"]["trace_samples"].append(
        {
            "service": services[0],
            "trace_id": f"trace-false-lead-{rng.randint(100, 999)}",
            "spans": [
                {
                    "service": services[0],
                    "operation": "GET /health",
                    "duration_ms": 740.0,
                    "status": "error",
                },
                {
                    "service": services[-1],
                    "operation": "background sync",
                    "duration_ms": 710.0,
                    "status": "timeout",
                }
            ],
            "error": "background timeout unrelated to customer path",
            "duration_ms": 740.0
        }
    )
    return "false_lead_trace"


def _variant_ops(payload: dict[str, Any], rng: Random) -> list[str]:
    operations = [
        _apply_noise_injection,
        _apply_evidence_shuffle,
        _apply_metric_jitter,
        _apply_timeline_shift,
        _apply_false_lead_trace,
    ]
    if rng.random() < 0.7:
        operations.append(_apply_consistent_rename)
    selected_count = min(len(operations), max(3, rng.randint(3, 6)))
    selected = rng.sample(operations, selected_count)
    return [operation(payload, rng) for operation in selected]


def generate_variant(base_scenario: Scenario, seed: int) -> Scenario:
    """Generate a deterministic variant from a base scenario."""

    payload = copy.deepcopy(scenario_to_payload(base_scenario))
    rng = Random(_stable_seed(base_scenario.id, seed))
    ops = _variant_ops(payload, rng)
    payload["variant_of"] = base_scenario.id
    payload["variant_seed"] = seed
    payload["variant_ops"] = ops
    payload["id"] = f"{base_scenario.id}__variant_{seed}"
    payload["title"] = f"{base_scenario.title} [variant {seed}]"
    variant = _scenario_from_payload(payload)
    if variant.ground_truth_root_cause_id != base_scenario.ground_truth_root_cause_id:
        raise ValueError("Variant changed the ground truth root cause id")
    if sorted(variant.allowed_mitigations) != sorted(base_scenario.allowed_mitigations):
        raise ValueError("Variant changed allowed mitigation semantics")
    return variant


def generate_scenario_suite(seed: int, num_variants_per_base: int = 5) -> list[Scenario]:
    """Generate a deterministic scenario suite from all base scenarios."""

    suite: list[Scenario] = []
    for index, base_scenario in enumerate(load_base_scenarios()):
        suite.append(base_scenario)
        for variant_index in range(num_variants_per_base):
            variant_seed = _stable_seed(seed, index, variant_index) % 1_000_000
            suite.append(generate_variant(base_scenario, variant_seed))
    return suite
