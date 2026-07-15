from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_benchmark_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("benchmark_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_output_shape(tmp_path) -> None:
    benchmark = _load_benchmark_module()
    rows = benchmark.run_benchmarks(
        seed=0,
        variants=1,
        max_steps=25,
        out_dir=str(tmp_path / "benchmarks"),
    )

    assert [row["agent"] for row in rows] == ["RandomAgent", "HeuristicAgent"]
    for row in rows:
        assert row["episodes"] == 16
        assert 0.0 <= row["pass_rate"] <= 1.0
        assert "avg_successful_steps" in row
        assert row["runtime_s"] >= 0.0

    table = benchmark.render_markdown_table(rows)
    assert "| Agent |" in table
    assert "RandomAgent" in table
    assert "HeuristicAgent" in table
