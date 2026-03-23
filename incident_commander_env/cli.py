"""Command-line interface for the Incident Commander environment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from . import IncidentCommanderEnv, load_replay, load_scenario, render_observation, replay_summary
from .eval.run_suite import build_agent, run_agent_on_suite, save_summary


InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]


def _tool_result_summary(tool_result: dict[str, Any] | None) -> str:
    if tool_result is None:
        return "none"
    return json.dumps(tool_result, sort_keys=True)


def _print_action_menu(observation: dict[str, Any], output_fn: OutputFn) -> None:
    output_fn("Available actions:")
    for index, action in enumerate(observation["available_actions"], start=1):
        output_fn(
            f"  {index}. {action['type']} {json.dumps(action['arg_schema'], sort_keys=True)}"
        )


def _default_args(observation: dict[str, Any], action_type: str) -> dict[str, Any]:
    catalog = observation["action_catalog"]
    incident = observation["incident"]
    verification_targets = observation["resolution_hints"]["verification_targets"]
    required_updates = observation["resolution_hints"]["required_updates"]

    if action_type == "create_incident":
        return {"title": f"{incident['primary_service']} incident", "severity": observation["severity"]}
    if action_type == "get_metrics":
        target = verification_targets[0]
        return {
            "service": target["service"],
            "metric": target["metric"],
            "window_steps": 1,
            "agg": "raw",
        }
    if action_type == "get_logs":
        query = catalog["query_hints"][0] if catalog["query_hints"] else "error"
        return {
            "service": catalog["log_service"],
            "query": query,
            "window_steps": 6,
            "limit": 10,
            "page": 0,
        }
    if action_type == "get_trace_sample" and catalog["trace_samples"]:
        return dict(catalog["trace_samples"][0])
    if action_type == "search_recent_deploys" and catalog["rollback_options"]:
        return {"service": catalog["rollback_options"][0]["service"], "window_steps": 6}
    if action_type == "diff_config" and catalog["config_diff_options"]:
        return dict(catalog["config_diff_options"][0])
    if action_type == "view_runbook" and catalog["runbook_services"]:
        return {"service": catalog["runbook_services"][0], "section": "triage"}
    if action_type == "post_update":
        template_id = required_updates[0]["template_id"] if required_updates else "status"
        audience = required_updates[0]["audience"] if required_updates else "internal"
        fields = {"summary": "Investigating", "eta": "10 minutes"}
        if template_id == "resolved":
            fields = {"summary": "Recovered", "customer_impact": "Resolved"}
        return {"audience": audience, "template_id": template_id, "fields": fields}
    if action_type == "apply_mitigation":
        mitigation_id = observation["allowed_mitigations"][0]
        return {"mitigation_id": mitigation_id}
    if action_type == "toggle_feature_flag":
        option = catalog["feature_flags"][0]
        return {"flag": option["flag"], "enabled": not option["current_enabled"]}
    if action_type == "apply_config_patch" and catalog["config_patches"]:
        return dict(catalog["config_patches"][0])
    if action_type == "rollback_deploy" and catalog["rollback_options"]:
        return dict(catalog["rollback_options"][0])
    if action_type == "restart_service":
        return {"service": incident["primary_service"]}
    if action_type == "scale_service":
        return {"service": incident["primary_service"], "replicas": 4}
    if action_type == "run_health_check":
        return {"service": incident["primary_service"]}
    if action_type == "wait":
        return {"steps": 1}
    if action_type == "confirm_metrics_normalized":
        return dict(verification_targets[0])
    if action_type == "declare_resolved":
        mitigation_id = observation["allowed_mitigations"][0]
        root_cause_id = observation["resolution_hints"]["root_cause_candidates"][0]
        return {
            "root_cause_id": root_cause_id,
            "mitigation_id": mitigation_id,
            "summary": "Manual resolution attempt",
        }
    if action_type == "declare_failed":
        return {"reason": "Operator ended the episode"}
    return {}


def _read_action(
    observation: dict[str, Any],
    input_fn: InputFn,
    output_fn: OutputFn,
) -> dict[str, Any] | None:
    _print_action_menu(observation, output_fn)
    raw = input_fn("Enter action JSON, action number, or q: ").strip()
    if raw.casefold() in {"q", "quit", "exit"}:
        return None
    if raw.isdigit():
        action_index = int(raw) - 1
        actions = observation["available_actions"]
        if not 0 <= action_index < len(actions):
            raise ValueError("Unknown action number")
        action_type = actions[action_index]["type"]
        default_args = _default_args(observation, action_type)
        output_fn(f"Default args: {json.dumps(default_args, sort_keys=True)}")
        args_raw = input_fn("Args JSON (blank to accept defaults): ").strip()
        args = default_args if not args_raw else json.loads(args_raw)
        return {"type": action_type, "args": args}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Action JSON must be an object")
    return parsed


def run_play(args: argparse.Namespace, input_fn: InputFn, output_fn: OutputFn) -> int:
    """Run the interactive play loop."""

    env = IncidentCommanderEnv(max_steps=args.max_steps, scenario=load_scenario(args.scenario))
    observation = env.reset(seed=args.seed)
    output_fn(render_observation(observation))

    while True:
        try:
            action = _read_action(observation, input_fn, output_fn)
        except Exception as exc:  # noqa: BLE001 - CLI should keep going
            output_fn(f"Invalid input: {exc}")
            continue

        if action is None:
            break

        observation, reward, done, info = env.step(action)
        output_fn("")
        output_fn(render_observation(observation))
        output_fn(f"Reward: {reward:.2f}")
        output_fn(f"Done: {done}")
        output_fn(f"Resolution: {info.get('resolution')}")
        output_fn(f"Fail reasons: {info.get('failure_reasons')}")
        output_fn(f"Tool result: {_tool_result_summary(info.get('tool_result'))}")
        if done:
            break

    replay = env.get_replay()
    if replay:
        replay_dir = Path(args.out_dir)
        replay_dir.mkdir(parents=True, exist_ok=True)
        replay_path = replay_dir / f"{replay[-1]['episode_id']}.jsonl"
        env.save_replay(str(replay_path))
        output_fn(f"Saved replay to {replay_path}")
    return 0


def _render_replay_event(event: dict[str, Any]) -> str:
    obs = event["obs"]
    return "\n".join(
        [
            f"Episode: {event['episode_id']}",
            f"Scenario: {event['scenario_id']}",
            f"Seed: {event['seed']}",
            f"Step: {event['t']}",
            f"Status: {obs['status']}",
            f"Alerts: {', '.join(obs['alert_ids']) or 'none'}",
            f"Evidence: {json.dumps(obs['evidence_flags'], sort_keys=True)}",
            f"Metrics: {json.dumps(obs['metrics_snapshot'], sort_keys=True)}",
            f"Action: {json.dumps(event['action'], sort_keys=True)}",
            f"Reward: {event['reward']}",
            f"Done: {event['done']}",
            f"Resolution: {event['info'].get('resolution')}",
            f"Fail reasons: {event['info'].get('failure_reasons', [])}",
        ]
    )


def run_replay(args: argparse.Namespace, input_fn: InputFn, output_fn: OutputFn) -> int:
    """Replay an episode from disk."""

    events = load_replay(args.path)
    if not events:
        output_fn("Replay is empty.")
        return 0

    index = 0
    while True:
        output_fn(_render_replay_event(events[index]))
        command = input_fn("(n)ext, (p)rev, (q)uit: ").strip().casefold()
        if command in {"q", "quit", "exit"}:
            break
        if command in {"n", ""}:
            index = min(len(events) - 1, index + 1)
        elif command == "p":
            index = max(0, index - 1)

    output_fn(json.dumps(replay_summary(events), sort_keys=True))
    return 0


def run_suite_command(args: argparse.Namespace, output_fn: OutputFn) -> int:
    """Run one benchmark suite from the CLI."""

    agent = build_agent(args.agent)
    summary = run_agent_on_suite(
        agent=agent,
        seed=args.seed,
        num_variants_per_base=args.variants,
        max_steps=args.max_steps,
        artifact_dir=args.out,
    )
    summary_path = save_summary(summary, args.out)
    output_fn(json.dumps(summary, indent=2, sort_keys=True))
    output_fn(f"Saved summary to {summary_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""

    parser = argparse.ArgumentParser(prog="ic", description="Incident Commander RL environment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    play = subparsers.add_parser("play", help="Play one scenario interactively")
    play.add_argument("--scenario", required=True, help="Scenario id or alias")
    play.add_argument("--seed", required=True, type=int, help="Deterministic seed")
    play.add_argument("--max-steps", type=int, default=25, help="Episode step cap")
    play.add_argument("--out-dir", default="replays", help="Directory for saved replay logs")

    replay = subparsers.add_parser("replay", help="Replay a saved JSONL episode")
    replay.add_argument("path", help="Path to replay JSONL")

    suite = subparsers.add_parser("suite", help="Run the deterministic benchmark suite")
    suite.add_argument("--agent", choices=("random", "heuristic"), required=True)
    suite.add_argument("--seed", required=True, type=int)
    suite.add_argument("--variants", type=int, default=5, help="Variants per base scenario")
    suite.add_argument("--max-steps", type=int, default=25)
    suite.add_argument("--out", default="eval_artifacts", help="Output directory")
    return parser


def main(
    argv: list[str] | None = None,
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
) -> int:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "play":
        return run_play(args, input_fn=input_fn, output_fn=output_fn)
    if args.command == "replay":
        return run_replay(args, input_fn=input_fn, output_fn=output_fn)
    if args.command == "suite":
        return run_suite_command(args, output_fn=output_fn)
    raise ValueError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
