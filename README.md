# Incident Commander RL Environment

This repository contains a deterministic reinforcement-learning environment for incident response. The goal is to model realistic operational work rather than a toy puzzle: incidents require investigation, communication, concrete mitigations, waiting for recovery, and explicit verification before resolution is accepted.

The environment is designed to be benchmarkable. Scenario packs are deterministic under seed, variants are procedurally generated from base incidents, replays are persistable and replayable as JSONL, and the benchmark harness surfaces failure reasons instead of only pass/fail outcomes.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Run tests

```bash
pytest -q
```

## CLI quickstart

Play one incident interactively:

```bash
ic play --scenario svc-checkout-regression --seed 0
```

Run the deterministic benchmark suite:

```bash
ic suite --agent heuristic --seed 0 --variants 5 --out eval_artifacts
```

Replay a saved episode:

```bash
ic replay eval_artifacts/failed_replays/<file>.jsonl
```

You can also invoke the CLI without installation using:

```bash
python -m incident_commander_env.cli suite --agent heuristic --seed 0 --variants 5 --out eval_artifacts
```

## CLI commands

`ic play --scenario <id> --seed <int>`

- Prints each structured observation using the CLI renderer.
- Shows available action types and arg schemas.
- Accepts either raw action JSON or a numbered action selection with default args.
- Saves a replay to `./replays/<episode_id>.jsonl` when the session ends.

`ic suite --agent random|heuristic --seed <int> --variants <int> --out <dir>`

- Runs the benchmark suite over all base scenarios plus generated variants.
- Prints pass rate per scenario, overall pass rate, average steps to successful resolution, and a failure histogram.
- Writes failed replays to `<out>/failed_replays/`.
- Writes a deterministic machine-readable summary to `<out>/summary.json`.

`ic replay <path_to_jsonl>`

- Loads a saved replay and lets you step through events with `n`, `p`, and `q`.
- Shows compact observation summaries, actions, rewards, fail reasons, and final resolution status.

## Replay files

Replay entries are stored as JSONL. Each line records:

- `episode_id`
- `scenario_id`
- `seed`
- `t`
- compact observation summary
- action
- reward
- done
- `info`, including `resolution` and `failure_reasons`

The replay summary aggregates total reward, total steps, final resolution status, and a histogram of the most common fail reasons. This makes it practical to inspect why an agent failed without rerunning the entire episode.
