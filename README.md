# Incident Commander RL Environment

This project is a reinforcement learning environment for real-world incident response work. Instead of treating operations like a toy control problem, it models the actual flow of handling production issues: triaging what is broken, making sense of noisy signals, choosing a mitigation that matches the situation, verifying that users are no longer impacted, and communicating clearly while the system recovers.

The scenarios are built around the kinds of failures software teams see in practice: a bad deploy that breaks checkout, exhausted database connections under burst traffic, queue backlogs, dependency outages, retry storms, DNS mistakes, memory leaks, and permission regressions. The point is not to reward an agent for guessing a hidden label. The point is to evaluate whether it can behave like a competent engineer under pressure.

## Why this exists

If you want to train or evaluate agents for engineering work, they need environments that look more like production than like a game. In a real incident, the agent has to gather evidence, coordinate updates, choose a concrete change, wait for the system to settle, and prove the service is healthy before calling the issue resolved. That is the standard this environment is built around.

The repository includes:

- a deterministic Gymnasium-style environment API
- eight deep base incident scenarios with seeded variants
- strict action validation and resolution gating
- an interactive CLI for stepping through incidents by hand
- a benchmark harness with baseline agents

## Requirements

- Python `3.10+`
- `pip`

If you are on macOS and your default `python3` is older, install a newer version first. Homebrew is the easiest path:

```bash
brew install python@3.12
```

If you want `python3` to refer to that install in new shells, add:

```bash
export PATH="/usr/local/opt/python@3.12/libexec/bin:$PATH"
```

to your `~/.zshrc`, then reload your shell.

## Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -V
python -m ensurepip --upgrade
python -m pip install --upgrade pip
python -m pip install -e .
```

After install, the CLI should be available:

```bash
ic --help
```

## Run tests

```bash
pytest -q
```

## Quickstart

Play through a checkout deploy regression by hand:

```bash
ic play --scenario svc-checkout-regression --seed 0
```

Run the evaluation suite with the heuristic baseline:

```bash
ic suite --agent heuristic --seed 0 --variants 5 --out eval_artifacts
```

Step through a saved run:

```bash
ic replay eval_artifacts/failed_replays/<file>.jsonl
```

If you have not installed the console script yet, you can run the CLI directly:

```bash
python -m incident_commander_env.cli play --scenario svc-checkout-regression --seed 0
```

## What it trains or evaluates

Agents in this environment are expected to do the kinds of things an on-call engineer or incident commander would do in a live production issue:

- identify which service is likely at fault
- investigate using metrics, logs, traces, deploy history, and config changes
- choose a mitigation that actually matches the evidence
- avoid risky or irrelevant actions that make the incident worse
- verify that the service has recovered before declaring success
- communicate progress as the incident unfolds

In other words, this environment is less about memorizing a solution and more about practicing disciplined operational judgment.

## CLI overview

`ic play --scenario <id> --seed <int>`

- Starts an interactive incident session.
- Shows the current state, available actions, and action argument schemas.
- Accepts either raw JSON actions or a numbered action selection.

`ic suite --agent random|heuristic --seed <int> --variants <int> --out <dir>`

- Runs a deterministic benchmark over the scenario suite.
- Prints pass rates, average resolution steps, and common failure reasons.
- Writes failed runs and a summary file to the output directory.

`ic replay <path_to_jsonl>`

- Opens a saved episode and lets you walk through it step by step.

## Base scenarios

The current scenario pack includes:

- deploy regression caused by a bad downstream endpoint config
- database connection exhaustion during traffic spikes
- queue backlog with downstream timeout pressure
- partial dependency outage requiring graceful degradation
- memory leak after deploy
- DNS / networking misconfiguration
- thundering herd from aggressive retry behavior
- permission failure after a security policy change

## Project structure

The main package lives in `incident_commander_env/`. The most important pieces are:

- `env.py`: environment state and step logic
- `scenario.py`: scenario loading and public scenario metadata
- `variants.py`: deterministic scenario variant generation
- `observation.py`: structured observations for agents and the CLI
- `validation.py`: strict action validation
- `scorer.py`: deterministic reward shaping and resolution checks
- `cli.py`: interactive CLI and benchmark entrypoint

## Notes

- The environment is deterministic under seed.
- Episodes are capped at 25 steps.
- Resolution is intentionally strict: investigation alone is not enough, and mitigation alone is not enough. The agent has to prove the system recovered.
