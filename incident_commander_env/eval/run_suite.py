"""Evaluation harness for Stage 3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..env import IncidentCommanderEnv
from ..replay import replay_summary
from ..variants import generate_scenario_suite
from .baselines import HeuristicAgent, RandomAgent


def build_agent(agent_name: str) -> Any:
    """Build one baseline agent by name."""

    normalized = agent_name.casefold()
    if normalized == "random":
        return RandomAgent()
    if normalized == "heuristic":
        return HeuristicAgent()
    raise KeyError(f"Unknown agent: {agent_name}")


def run_agent_on_suite(
    agent: Any,
    seed: int,
    num_variants_per_base: int = 2,
    max_steps: int = 25,
    artifact_dir: str = "eval_artifacts",
) -> dict[str, Any]:
    """Run one agent across the deterministic scenario suite."""

    suite = generate_scenario_suite(seed, num_variants_per_base=num_variants_per_base)
    artifact_path = Path(artifact_dir) / "failed_replays"
    artifact_path.mkdir(parents=True, exist_ok=True)

    pass_rate: dict[str, dict[str, int]] = {}
    fail_histogram: dict[str, int] = {}
    total_steps = 0
    successful_steps = 0
    successes = 0

    for index, scenario in enumerate(suite):
        env = IncidentCommanderEnv(max_steps=max_steps, scenario=scenario)
        observation = env.reset(seed=seed + index)
        agent.reset(scenario, seed + index)
        info: dict[str, Any] | None = None

        done = False
        while not done:
            action = agent.act(observation, info)
            observation, _, done, info = env.step(action)

        summary = replay_summary(env.get_replay())
        scenario_type = scenario.variant_of or scenario.id
        pass_rate.setdefault(scenario_type, {"passed": 0, "total": 0})
        pass_rate[scenario_type]["total"] += 1
        total_steps += len(env.get_replay())
        if summary["resolution"] == "success":
            pass_rate[scenario_type]["passed"] += 1
            successes += 1
            successful_steps += len(env.get_replay())
        else:
            for reason, count in summary["failure_reasons"].items():
                fail_histogram[reason] = fail_histogram.get(reason, 0) + count
            env.save_replay(str(artifact_path / f"{agent.__class__.__name__}_{scenario.id}_{seed + index}.jsonl"))

    return {
        "agent": agent.__class__.__name__,
        "suite_size": len(suite),
        "avg_steps_to_resolution": round(successful_steps / successes, 4) if successes else 0.0,
        "avg_steps_all_episodes": round(total_steps / len(suite), 4) if suite else 0.0,
        "pass_rate_per_scenario": {
            key: round(value["passed"] / value["total"], 4) if value["total"] else 0.0
            for key, value in sorted(pass_rate.items())
        },
        "overall_pass_rate": round(successes / len(suite), 4) if suite else 0.0,
        "common_fail_reasons": dict(sorted(fail_histogram.items())),
    }


def save_summary(summary: dict[str, Any], out_dir: str) -> Path:
    """Persist a suite summary deterministically."""

    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "summary.json"
    with target.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, sort_keys=True, indent=2)
        handle.write("\n")
    return target


def run_suite(
    seed: int = 0,
    num_variants_per_base: int = 2,
    max_steps: int = 25,
    artifact_dir: str = "eval_artifacts",
) -> dict[str, Any]:
    """Run both baseline agents across the deterministic suite."""

    results = {}
    for agent in (RandomAgent(), HeuristicAgent()):
        results[agent.__class__.__name__] = run_agent_on_suite(
            agent=agent,
            seed=seed,
            num_variants_per_base=num_variants_per_base,
            max_steps=max_steps,
            artifact_dir=artifact_dir,
        )
    return results
