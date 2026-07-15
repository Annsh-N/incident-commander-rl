# Environment Contract

Incident Commander exposes a small RL-style API for deterministic incident
episodes. The goal is to evaluate whether an agent can investigate, mitigate,
verify, and communicate during a production-inspired outage.

## API

```python
from incident_commander_env import IncidentCommanderEnv

env = IncidentCommanderEnv()
observation = env.reset(seed=0)
observation, reward, done, info = env.step(action)
```

`reset(seed)` initializes a deterministic episode and returns the first
observation.

`step(action)` validates and applies one action, advances simulated time, and
returns:

- `observation`: structured environment state visible to the agent;
- `reward`: deterministic dense reward for the action;
- `done`: whether the episode terminated;
- `info`: validation errors, tool results, resolution status, and failure
  reasons.

## Observation

Observations are JSON-like dictionaries. Important fields include:

- `step`, `severity`, and `status`;
- active alerts and incident messages;
- recent actions and summarized tool results;
- metric snapshots;
- typed action schemas;
- allowed mitigations and mitigation action catalog;
- verification targets and required communication updates;
- evidence flags showing which required evidence has been found.

The environment intentionally exposes structured hints so baseline policies are
reproducible and easy to audit. Benchmark results should be interpreted with
that in mind.

## Actions

Actions are dictionaries with exactly two keys:

```python
{"type": "get_logs", "args": {"service": "checkout-service", "query": "timeout", "window_steps": 5, "limit": 10, "page": 0}}
```

The action surface includes investigation, coordination, mitigation,
verification, and terminal actions:

- inspect metrics, logs, traces, deploys, config diffs, services, and runbooks;
- create an incident, assign roles, request help, and post updates;
- propose a mitigation and execute concrete changes;
- wait for stabilization and confirm metrics normalized;
- declare success or failure.

Invalid actions receive a penalty and return a validation error in `info`.

## Reward And Termination

Each step starts with a small time penalty. Positive reward is given for useful
investigation categories, required evidence, timely incident creation, and
required communication. Unsafe, repeated, or invalid behavior is penalized.

A successful resolution requires all of the following:

- incident record created;
- enough investigation categories used;
- required scenario evidence found;
- concrete mitigation planned before execution;
- causal change applied;
- at least one wait after the change;
- required metrics verified as normalized;
- required communication updates posted;
- correct root cause and mitigation declared.

Episodes terminate when the agent declares a resolution/failure or reaches the
maximum step count.
