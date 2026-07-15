"""Run baseline benchmarks and print a Markdown results table."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from incident_commander_env.eval.baselines import HeuristicAgent, RandomAgent
from incident_commander_env.eval.run_suite import run_agent_on_suite, save_summary


def _format_pass_rate(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_steps(value: float) -> str:
    return "-" if value == 0.0 else f"{value:.1f}"


def run_benchmarks(seed: int, variants: int, max_steps: int, out_dir: str) -> list[dict[str, Any]]:
    """Run all baseline agents and return benchmark rows."""

    output_root = Path(out_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for agent in (RandomAgent(), HeuristicAgent()):
        agent_name = agent.__class__.__name__
        artifact_dir = output_root / agent_name
        start = time.perf_counter()
        summary = run_agent_on_suite(
            agent=agent,
            seed=seed,
            num_variants_per_base=variants,
            max_steps=max_steps,
            artifact_dir=str(artifact_dir),
        )
        elapsed_s = round(time.perf_counter() - start, 4)
        save_summary(summary, str(artifact_dir))
        rows.append(
            {
                "agent": agent_name,
                "variants_per_base": variants,
                "episodes": summary["suite_size"],
                "pass_rate": summary["overall_pass_rate"],
                "avg_successful_steps": summary["avg_steps_to_resolution"],
                "runtime_s": elapsed_s,
            }
        )

    summary_path = output_root / "benchmark_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, sort_keys=True, indent=2)
        handle.write("\n")
    return rows


def render_markdown_table(rows: list[dict[str, Any]]) -> str:
    """Render benchmark rows as a Markdown table."""

    lines = [
        "| Agent | Variants per base | Episodes | Pass rate | Avg successful steps | Runtime |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {agent} | {variants} | {episodes} | {pass_rate} | {steps} | {runtime:.2f}s |".format(
                agent=row["agent"],
                variants=row["variants_per_base"],
                episodes=row["episodes"],
                pass_rate=_format_pass_rate(row["pass_rate"]),
                steps=_format_steps(row["avg_successful_steps"]),
                runtime=row["runtime_s"],
            )
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark CLI parser."""

    parser = argparse.ArgumentParser(description="Run Incident Commander baseline benchmarks.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variants", type=int, default=5, help="Variants per base scenario.")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--out", default="benchmark_results")
    return parser


def main() -> int:
    """Run the benchmark CLI."""

    args = build_parser().parse_args()
    rows = run_benchmarks(
        seed=args.seed,
        variants=args.variants,
        max_steps=args.max_steps,
        out_dir=args.out,
    )
    print(render_markdown_table(rows))
    print(f"\nSaved summaries to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
