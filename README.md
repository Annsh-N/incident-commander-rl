# Incident Commander RL Environment

Incident Commander is a deterministic RL-style environment for evaluating agents
on production incident response. It models the operational loop an engineer
would follow during an outage: inspect noisy signals, gather evidence, choose a
safe mitigation, wait for the system to stabilize, verify recovery, and
communicate status before declaring the incident resolved.

The environment is synthetic, but the scenarios are based on common production
failure modes: bad deploys, database connection exhaustion, queue backlogs,
partial dependency outages, memory leaks, DNS mistakes, retry storms, and
permission regressions.

## At a Glance

| Capability | Current state |
| --- | --- |
| Base scenarios | 8 production-inspired incidents |
| Seeded variants | 40 variants with `--variants 5` |
| Action surface | 24 typed actions |
| Validation | Strict action schemas and scenario-specific checks |
| Replay | Deterministic JSONL episode logs |
| CLI | `play`, `suite`, and `replay` commands |
| Baselines | Random and structured heuristic agents |
| Tests | 8 passing tests |

## Why This Exists

Most agent benchmarks do not look like real engineering work. In an incident,
the agent must handle partial evidence, avoid risky actions, communicate with
humans, and prove the service is healthy before calling the issue resolved.
This project makes those requirements explicit and reproducible.

The repository includes:

- a Gymnasium-inspired `reset(seed)` / `step(action)` API;
- eight deep incident scenarios with deterministic seeded variants;
- strict action validation and resolution gating;
- an interactive CLI for stepping through incidents by hand;
- a benchmark harness with baseline agents;
- JSONL replay logs for failed or interesting episodes.

## Setup

Requirements:

- Python `3.10+`
- `pip`

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

After install, the CLI should be available:

```bash
ic --help
```

Run tests:

```bash
pytest -q
```

Expected result:

```text
8 passed
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

Run both baselines and print a Markdown results table:

```bash
python scripts/benchmark.py --seed 0 --variants 5 --out benchmark_results
```

Step through a saved run:

```bash
ic replay eval_artifacts/failed_replays/<file>.jsonl
```

## Benchmark Results

These results were measured locally with:

```bash
ic suite --agent random --seed 0 --variants 5 --out eval_artifacts/random
ic suite --agent heuristic --seed 0 --variants 5 --out eval_artifacts/heuristic
python scripts/benchmark.py --seed 0 --variants 25 --out benchmark_results
```

| Agent | Episodes | Pass rate | Avg successful steps | Runtime |
| --- | ---: | ---: | ---: | ---: |
| RandomAgent | 48 | 0.0% | - | ~0.38s |
| HeuristicAgent | 48 | 62.5% | 15.0 | ~0.47s |
| RandomAgent | 208 | 0.0% | - | ~1.70s |
| HeuristicAgent | 208 | 62.5% | 15.0 | ~2.07s |

The heuristic baseline is intentionally transparent: it uses structured
observations and public scenario hints exposed by the environment. Treat these
numbers as a reproducibility and scenario-difficulty check, not as model
accuracy.

## Environment Contract

The environment follows a small RL-style contract:

```python
observation = env.reset(seed=0)
observation, reward, done, info = env.step(action)
```

Actions are JSON-like dictionaries:

```python
{"type": "get_logs", "args": {"service": "checkout-service", "query": "timeout", "window_steps": 5, "limit": 10, "page": 0}}
```

Resolution is strict. A successful episode requires enough investigation,
evidence, a concrete mitigation, a wait for stabilization, metric verification,
and required communication updates. See `docs/ENVIRONMENT.md` for the full
contract.

## Base Scenarios

The current scenario pack includes:

- deploy regression caused by a bad downstream endpoint config;
- database connection exhaustion during traffic spikes;
- queue backlog with downstream timeout pressure;
- partial dependency outage requiring graceful degradation;
- memory leak after deploy;
- DNS / networking misconfiguration;
- thundering herd from aggressive retry behavior;
- permission failure after a security policy change.

## Project Structure

The main package lives in `incident_commander_env/`.

- `env.py`: environment state and step logic
- `scenario.py`: scenario loading and public scenario metadata
- `variants.py`: deterministic scenario variant generation
- `observation.py`: structured observations for agents and the CLI
- `validation.py`: strict action validation
- `scorer.py`: deterministic reward shaping and resolution checks
- `cli.py`: interactive CLI and benchmark entrypoint

Additional docs:

- `docs/ENVIRONMENT.md`: observation, action, reward, and termination contract
- `docs/BENCHMARKS.md`: benchmark commands, results, and interpretation
- `docs/SCENARIO_AUTHORING.md`: how to add scenarios safely

## Limitations

- The incidents are synthetic and are not connected to live telemetry.
- Baselines are deterministic policies, not trained RL agents.
- The current API is Gymnasium-inspired, but this package does not yet expose a
  full `gymnasium.Env` adapter with spaces.
- Structured hints are exposed intentionally so baseline behavior is
  reproducible and easy to inspect.
