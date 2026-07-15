# Scenario Authoring

Scenarios are JSON files under `incident_commander_env/scenarios/`. Each
scenario describes one production-inspired incident and the evidence needed to
resolve it.

## Required Scenario Pieces

A scenario should define:

- services and dependencies;
- timeline events with alerts and messages;
- metric profiles for degraded and stabilized states;
- logs, deploy history, config diffs, traces, runbook snippets, and team help
  responses;
- allowed, safe, forbidden, and total mitigation identifiers;
- concrete mitigation rules that map actions to mitigations;
- resolution rubric: required evidence, updates, verifications, investigation
  count, and incident-creation deadline;
- evidence markers used by scoring and tests.

## Design Rules

Each scenario should be solvable but not trivial.

- Include at least one false lead or distractor signal.
- Require investigation before the correct mitigation.
- Make unsafe or irrelevant mitigations possible.
- Require verification after the fix.
- Require communication before success.
- Keep ground truth stable across generated variants.

## Validation Expectations

Before a scenario is accepted:

```bash
pytest -q
python scripts/benchmark.py --seed 0 --variants 5 --out /tmp/ic_scenario_check
```

The scenario must satisfy:

- a scripted success path can resolve it;
- deterministic variants preserve root cause and allowed mitigations;
- key evidence remains discoverable in variants;
- replay round-trips remain deterministic;
- benchmark output includes pass rates and failure reasons.
