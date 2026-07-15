# Benchmarks

Benchmarks run deterministic baseline agents over the generated scenario suite.
They are intended to measure environment reproducibility and scenario
difficulty, not trained model accuracy.

## Commands

Run one CLI benchmark:

```bash
ic suite --agent heuristic --seed 0 --variants 5 --out eval_artifacts/heuristic
```

Run both baselines and print a Markdown table:

```bash
python scripts/benchmark.py --seed 0 --variants 5 --out benchmark_results
```

Use a larger deterministic suite:

```bash
python scripts/benchmark.py --seed 0 --variants 25 --out benchmark_results_25
```

## Local Results

| Agent | Variants per base | Episodes | Pass rate | Avg successful steps | Runtime |
| --- | ---: | ---: | ---: | ---: | ---: |
| RandomAgent | 5 | 48 | 0.0% | - | ~0.38s |
| HeuristicAgent | 5 | 48 | 62.5% | 15.0 | ~0.47s |
| RandomAgent | 25 | 208 | 0.0% | - | ~1.70s |
| HeuristicAgent | 25 | 208 | 62.5% | 15.0 | ~2.07s |

The suite size is `8 * (variants + 1)`: eight base scenarios plus the requested
number of deterministic variants per base scenario.

## Baselines

`RandomAgent` samples from valid-ish candidate actions. It is useful as a lower
bound and should not resolve scenarios reliably.

`HeuristicAgent` is a deterministic policy that uses public observations,
structured action catalogs, and tool outputs. It is intentionally transparent,
so its pass rate should be read as a structured-policy baseline rather than
evidence of learned behavior.

## Interpreting Failures

Failed runs are saved as JSONL replays. Common failure reasons include:

- missing required evidence;
- insufficient investigation;
- no concrete change;
- declaring before waiting after a mitigation;
- missing metric verification;
- wrong root cause or mitigation;
- timeout before stable resolution.

Replay failed runs with:

```bash
ic replay eval_artifacts/failed_replays/<file>.jsonl
```
