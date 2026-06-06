"""Tests for the experiment framework module."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, r"d:\Desktop\minicode\py-src")

import pytest

from minicode.experiments.configs import (
    ArchitectureConfig,
    BenchmarkConfig,
    ExperimentConfig,
    SINGLE_AGENT_CONFIG,
    SEQUENTIAL_CONFIG,
    PARALLEL_CONFIG,
    HIERARCHICAL_CONFIG,
    CONSENSUS_CONFIG,
    TOOL_MEDIATED_CONFIG,
    ADAPTIVE_CONFIG,
    ALL_ARCHITECTURE_CONFIGS,
    SWE_BENCH_CONFIG,
    NL2REPO_CONFIG,
    get_pilot_configs,
    generate_experiment_configs,
)
from minicode.experiments.experiment_logger import (
    ExperimentLogger,
    ExperimentRun,
    RunStatus,
    TaskResult,
)
from minicode.experiments.metrics import (
    ExperimentMetrics,
    compute_metrics,
    aggregate_runs,
    compute_improvement_over_baseline,
)
from minicode.experiments.analyzers.swe_bench_eval import (
    SWEBenchEvaluator,
    SWEBenchTask,
    SWEBenchResult,
)
from minicode.experiments.analyzers.nl2repo_eval import (
    NL2RepoEvaluator,
    NL2RepoTask,
    NL2RepoResult,
)


class TestConfigs:
    """Test configuration definitions."""

    def test_all_architectures_have_unique_names(self):
        names = [c.name for c in ALL_ARCHITECTURE_CONFIGS]
        assert len(names) == len(set(names))

    def test_single_agent_is_not_multi(self):
        assert not SINGLE_AGENT_CONFIG.is_multi_agent
        assert SINGLE_AGENT_CONFIG.agent_count == 1

    def test_all_multi_agent_have_count_gt_1(self):
        for config in ALL_ARCHITECTURE_CONFIGS:
            if config.is_multi_agent:
                assert config.agent_count > 1

    def test_adaptive_is_multi_agent(self):
        assert ADAPTIVE_CONFIG.is_multi_agent
        assert ADAPTIVE_CONFIG.adaptive
        assert ADAPTIVE_CONFIG.max_adjustments == 3

    def test_config_to_dict(self):
        d = SINGLE_AGENT_CONFIG.to_dict()
        assert d["name"] == "single"
        assert not d["is_multi_agent"]

    def test_generate_experiment_configs_limited(self):
        configs = generate_experiment_configs(
            architectures=[SINGLE_AGENT_CONFIG],
            benchmarks=[SWE_BENCH_CONFIG],
        )
        assert len(configs) == 1
        assert configs[0].experiment_id == "swe_bench_single"

    def test_pilot_configs(self):
        configs = get_pilot_configs()
        assert len(configs) == 3
        names = {c.architecture.name for c in configs}
        assert names == {"single", "sequential", "hierarchical"}
        for c in configs:
            assert c.benchmark.max_tasks == 5
            assert c.benchmark.num_runs == 1

    def test_benchmark_config_timeout(self):
        assert SWE_BENCH_CONFIG.timeout_per_task_seconds == 1800
        assert NL2REPO_CONFIG.timeout_per_task_seconds == 3600

    def test_experiment_config_to_dict(self):
        config = ExperimentConfig(
            experiment_id="test_exp",
            architecture=SINGLE_AGENT_CONFIG,
            benchmark=SWE_BENCH_CONFIG,
        )
        d = config.to_dict()
        assert d["experiment_id"] == "test_exp"
        assert d["model_name"] == "claude-sonnet-4-20250514"
        assert d["seed"] == 42


class TestExperimentLogger:
    """Test the experiment logger."""

    def test_create_and_complete_run(self, tmp_path):
        logger = ExperimentLogger(str(tmp_path))
        run = logger.create_run(
            experiment_id="test_exp",
            architecture_name="single",
            benchmark_name="swe_bench",
            model_name="test-model",
        )
        assert run.status == RunStatus.RUNNING
        assert run.experiment_id == "test_exp"

        logger.complete_run(run.run_id, RunStatus.SUCCESS)
        assert run.status == RunStatus.SUCCESS
        assert run.end_time

    def test_add_task_result(self, tmp_path):
        logger = ExperimentLogger(str(tmp_path))
        run = logger.create_run("exp1", "single", "swe", "m1")

        task = TaskResult(
            task_id="task_1",
            status=RunStatus.SUCCESS,
            success=True,
            duration_seconds=10.0,
        )
        logger.add_task_result(run.run_id, task)

        assert run.task_count == 1
        assert run.pass_rate == 1.0

    def test_persist_and_reload(self, tmp_path):
        logger = ExperimentLogger(str(tmp_path))
        run = logger.create_run("exp1", "single", "swe", "m1")
        run.task_results.append(TaskResult(task_id="t1", success=True))
        logger.complete_run(run.run_id, RunStatus.SUCCESS)

        loaded = logger.load_run(run.run_id)
        assert loaded is not None
        assert loaded.experiment_id == "exp1"
        assert loaded.task_count == 1

    def test_get_runs_by_architecture(self, tmp_path):
        logger = ExperimentLogger(str(tmp_path))
        logger.create_run("e1", "single", "swe", "m1")
        logger.create_run("e2", "parallel", "swe", "m1")

        single_runs = logger.get_runs_by_architecture("single")
        assert len(single_runs) == 1

        parallel_runs = logger.get_runs_by_architecture("parallel")
        assert len(parallel_runs) == 1

    def test_get_summary(self, tmp_path):
        logger = ExperimentLogger(str(tmp_path))
        r1 = logger.create_run("e1", "single", "swe", "m1")
        r1.task_results = [TaskResult(task_id="t1", success=True)]
        logger.complete_run(r1.run_id)

        summary = logger.get_summary()
        assert "swe|single" in summary
        assert summary["swe|single"]["pass_rates"] == [1.0]


class TestMetrics:
    """Test metrics computation."""

    def test_compute_metrics_empty(self):
        run = ExperimentRun(experiment_id="test")
        metrics = compute_metrics(run)
        assert metrics.pass_rate == 0.0
        assert metrics.success_rate == 0.0

    def test_compute_metrics_all_pass(self):
        run = ExperimentRun(experiment_id="test")
        run.task_results = [
            TaskResult(task_id="t1", success=True, duration_seconds=5.0,
                       metrics={"input_tokens": 100, "output_tokens": 50}),
            TaskResult(task_id="t2", success=True, duration_seconds=10.0,
                       metrics={"input_tokens": 200, "output_tokens": 100}),
        ]
        metrics = compute_metrics(run)
        assert metrics.pass_rate == 1.0
        assert metrics.total_token_usage == 450
        assert metrics.estimated_cost_usd > 0

    def test_compute_metrics_partial_pass(self):
        run = ExperimentRun(experiment_id="test")
        run.task_results = [
            TaskResult(task_id="t1", success=True, duration_seconds=5.0, metrics={}),
            TaskResult(task_id="t2", success=False, status=RunStatus.FAILED, metrics={}),
        ]
        metrics = compute_metrics(run)
        assert metrics.pass_rate == 0.5
        assert metrics.error_rate == 0.5

    def test_aggregate_runs(self):
        r1 = ExperimentRun(experiment_id="e1", architecture_name="single", benchmark_name="swe")
        r1.task_results = [TaskResult(task_id="t1", success=True, metrics={})]

        r2 = ExperimentRun(experiment_id="e1", architecture_name="single", benchmark_name="swe")
        r2.task_results = [TaskResult(task_id="t1", success=False, status=RunStatus.FAILED, metrics={})]

        agg = aggregate_runs([r1, r2])
        assert agg.pass_rate == 0.5

    def test_compute_improvement_over_baseline(self):
        baseline = ExperimentMetrics(pass_rate=0.5, estimated_cost_usd=1.0, error_rate=0.2,
                                     mean_duration_seconds=100.0)
        treatment = ExperimentMetrics(pass_rate=0.75, estimated_cost_usd=2.0, error_rate=0.1,
                                      mean_duration_seconds=80.0)

        improvement = compute_improvement_over_baseline(treatment, baseline)
        assert improvement["pass_rate_improvement"] == 0.5
        assert improvement["speedup"] > 1.0
        assert improvement["error_rate_diff"] == 0.1

    def test_metrics_to_csv_row(self):
        metrics = ExperimentMetrics(
            architecture_name="single",
            benchmark_name="swe",
            pass_rate=0.8,
        )
        row = metrics.to_csv_row()
        assert row["architecture_name"] == "single"
        assert row["pass_rate"] == "0.8000"


class TestSWEBenchEvaluator:
    """Test SWE-bench evaluation."""

    def test_load_tasks(self, tmp_path):
        jsonl = tmp_path / "tasks.jsonl"
        jsonl.write_text(json.dumps({
            "instance_id": "test_1",
            "repo": "test/repo",
            "problem_statement": "Fix bug",
            "base_commit": "abc123",
            "test_patch": "diff --git ...",
        }) + "\n")

        tasks = SWEBenchEvaluator.load_tasks(str(jsonl), max_tasks=10)
        assert len(tasks) == 1
        assert tasks[0].instance_id == "test_1"

    def test_extract_patch_from_markdown(self):
        output = """Here is the fix:

```diff
diff --git a/file.py b/file.py
index 123..456
--- a/file.py
+++ b/file.py
@@ -1 +1 @@
-old
+new
```

Done."""
        patch = SWEBenchEvaluator._extract_patch(output)
        assert "diff --git" in patch
        assert "+new" in patch

    def test_extract_patch_no_markers(self):
        output = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n-old\n+new"
        patch = SWEBenchEvaluator._extract_patch(output)
        assert "diff --git" in patch

    def test_compute_pass_rate(self):
        results = [
            SWEBenchResult(instance_id="1", resolved=True),
            SWEBenchResult(instance_id="2", resolved=False),
            SWEBenchResult(instance_id="3", resolved=True),
        ]
        stats = SWEBenchEvaluator().compute_pass_rate(results)
        assert stats["pass_rate"] == 2 / 3
        assert stats["resolved_count"] == 2
        assert stats["total_count"] == 3

    def test_empty_patch_fails(self):
        task = SWEBenchTask(
            instance_id="test",
            repo="test/repo",
            problem_statement="test",
            base_commit="abc",
            test_patch="",
        )
        result = SWEBenchEvaluator().evaluate_patch(task, "")
        assert not result.resolved
        assert "Empty" in result.error_message


class TestNL2RepoEvaluator:
    """Test NL2Repo evaluation."""

    def test_load_tasks(self, tmp_path):
        jsonl = tmp_path / "tasks.jsonl"
        jsonl.write_text(json.dumps({
            "task_id": "nl2r_1",
            "requirement_doc": "Build a calculator library",
            "test_dir": "tests",
            "expected_files": ["calculator.py"],
        }) + "\n")

        tasks = NL2RepoEvaluator.load_tasks(str(jsonl), max_tasks=10)
        assert len(tasks) == 1
        assert tasks[0].task_id == "nl2r_1"

    def test_parse_pytest_output(self):
        output = "collected 10 items\n\n...\n\n======= 8 passed, 2 failed in 0.5s ======="
        total, passed, failed = NL2RepoEvaluator._parse_pytest_output(output)
        assert total == 10
        assert passed == 8
        assert failed == 2

    def test_parse_pytest_all_pass(self):
        output = "10 passed in 0.3s"
        total, passed, failed = NL2RepoEvaluator._parse_pytest_output(output)
        assert total == 10
        assert passed == 10
        assert failed == 0

    def test_extract_files(self, tmp_path):
        output = """# File: main.py
```python
def hello():
    return "world"
```

# File: utils.py
```python
def add(a, b):
    return a + b
```"""
        NL2RepoEvaluator._extract_files(output, tmp_path)
        main_file = tmp_path / "main.py"
        utils_file = tmp_path / "utils.py"
        assert main_file.exists()
        assert utils_file.exists()
        assert "def hello" in main_file.read_text()

    def test_compute_pass_rate(self):
        results = [
            NL2RepoResult(task_id="1", pass_rate=0.8, total_tests=10, passed_tests=8, failed_tests=2),
            NL2RepoResult(task_id="2", pass_rate=1.0, total_tests=5, passed_tests=5, failed_tests=0),
        ]
        stats = NL2RepoEvaluator().compute_pass_rate(results)
        assert stats["mean_pass_rate"] == 0.9
        assert stats["total_tests"] == 15
        assert stats["total_passed"] == 13


class TestIntegration:
    """Integration tests for the experiment framework."""

    def test_full_pipeline_without_model(self, tmp_path):
        """Test the experiment pipeline without actual model calls."""
        from minicode.experiments.configs import get_pilot_configs

        configs = get_pilot_configs()
        assert len(configs) == 3

        logger = ExperimentLogger(str(tmp_path))
        for config in configs:
            run = logger.create_run(
                experiment_id=config.experiment_id,
                architecture_name=config.architecture.name,
                benchmark_name=config.benchmark.name,
                model_name=config.model_name,
                run_index=0,
            )
            run.task_results.append(TaskResult(task_id="pilot_1", success=True, metrics={
                "input_tokens": 500,
                "output_tokens": 200,
            }))
            logger.complete_run(run.run_id, RunStatus.SUCCESS)

        summary = logger.get_summary()
        assert len(summary) == 3

    def test_generate_experiment_matrix(self):
        configs = generate_experiment_configs(
            architectures=[SINGLE_AGENT_CONFIG, PARALLEL_CONFIG],
            benchmarks=[SWE_BENCH_CONFIG, NL2REPO_CONFIG],
        )
        assert len(configs) == 4

        ids = {c.experiment_id for c in configs}
        assert "swe_bench_single" in ids
        assert "swe_bench_parallel" in ids
        assert "nl2repo_single" in ids
        assert "nl2repo_parallel" in ids


class TestMLEBenchEvaluator:
    """Test MLE-bench evaluation."""

    def test_load_tasks(self, tmp_path):
        from minicode.experiments.analyzers.mle_bench_eval import MLEBenchEvaluator

        jsonl = tmp_path / "tasks.jsonl"
        jsonl.write_text(json.dumps({
            "competition_id": "titanic",
            "description": "Predict survival on Titanic",
            "metric": "accuracy",
            "time_limit_hours": 24,
        }) + "\n")

        tasks = MLEBenchEvaluator.load_tasks(str(jsonl), max_tasks=10)
        assert len(tasks) == 1
        assert tasks[0].competition_id == "titanic"
        assert tasks[0].metric == "accuracy"

    def test_extract_score_accuracy(self):
        from minicode.experiments.analyzers.mle_bench_eval import MLEBenchEvaluator

        output = "Training complete.\nAccuracy: 0.923\nDone."
        score = MLEBenchEvaluator._extract_score(output)
        assert score == 0.923

    def test_extract_score_f1(self):
        from minicode.experiments.analyzers.mle_bench_eval import MLEBenchEvaluator

        output = "F1-Score: 0.85"
        score = MLEBenchEvaluator._extract_score(output)
        assert score == 0.85

    def test_extract_score_percentage(self):
        from minicode.experiments.analyzers.mle_bench_eval import MLEBenchEvaluator

        output = "Score: 85.5"
        score = MLEBenchEvaluator._extract_score(output)
        assert score == 0.855

    def test_determine_medal(self):
        from minicode.experiments.analyzers.mle_bench_eval import MLEBenchEvaluator

        assert MLEBenchEvaluator._determine_medal(0.96) == "gold"
        assert MLEBenchEvaluator._determine_medal(0.90) == "silver"
        assert MLEBenchEvaluator._determine_medal(0.80) == "bronze"
        assert MLEBenchEvaluator._determine_medal(0.60) == ""

    def test_compute_summary(self):
        from minicode.experiments.analyzers.mle_bench_eval import (
            MLEBenchEvaluator, MLEBenchResult,
        )

        results = [
            MLEBenchResult(competition_id="c1", score=0.96, medal="gold"),
            MLEBenchResult(competition_id="c2", score=0.82, medal="bronze"),
            MLEBenchResult(competition_id="c3", score=0.60, medal=""),
        ]
        summary = MLEBenchEvaluator().compute_summary(results)
        assert summary["mean_score"] > 0.7
        assert summary["medal_counts"]["gold"] == 1
        assert summary["medal_counts"]["bronze"] == 1
        assert summary["medal_counts"]["none"] == 1
        assert summary["any_medal_rate"] == 2 / 3

    def test_extract_files_from_output(self, tmp_path):
        from minicode.experiments.analyzers.mle_bench_eval import MLEBenchEvaluator

        output = """# File: train.py
```python
import pandas as pd
def train():
    pass
```

# File: predict.py
```python
def predict():
    pass
```"""
        MLEBenchEvaluator._extract_files(output, tmp_path)
        assert (tmp_path / "train.py").exists()
        assert (tmp_path / "predict.py").exists()


class TestPaperBenchEvaluator:
    """Test PaperBench evaluation."""

    def test_load_tasks(self, tmp_path):
        from minicode.experiments.analyzers.paper_bench_eval import PaperBenchEvaluator

        jsonl = tmp_path / "tasks.jsonl"
        jsonl.write_text(json.dumps({
            "paper_id": "pp_001",
            "paper_title": "Attention Is All You Need",
            "paper_text": "The dominant sequence transduction models...",
            "total_points": 100,
            "time_limit_hours": 12,
        }) + "\n")

        tasks = PaperBenchEvaluator.load_tasks(str(jsonl), max_tasks=5)
        assert len(tasks) == 1
        assert tasks[0].paper_id == "pp_001"

    def test_eval_code_structure(self, tmp_path):
        from minicode.experiments.analyzers.paper_bench_eval import PaperBenchEvaluator

        (tmp_path / "module").mkdir()
        (tmp_path / "module" / "__init__.py").write_text("")
        (tmp_path / "main.py").write_text("def main(): pass")
        (tmp_path / "config.py").write_text("batch_size = 32")
        (tmp_path / "requirements.txt").write_text("torch>=2.0")
        (tmp_path / "README.md").write_text("# Paper Reproduction")

        score = PaperBenchEvaluator._eval_code_structure(tmp_path)
        assert score >= 0.5

    def test_eval_code_structure_empty(self, tmp_path):
        from minicode.experiments.analyzers.paper_bench_eval import PaperBenchEvaluator

        score = PaperBenchEvaluator._eval_code_structure(tmp_path)
        assert score == 0.0

    def test_eval_method_implementation(self, tmp_path):
        from minicode.experiments.analyzers.paper_bench_eval import PaperBenchEvaluator, PaperBenchTask

        (tmp_path / "model.py").write_text(
            "import torch\nclass Transformer:\n    def forward(self, x):\n        return x\n"
        )
        (tmp_path / "train.py").write_text(
            "def train():\n    # training loop\n    pass\n"
        )

        task = PaperBenchTask(paper_id="test", paper_text="test")
        score = PaperBenchEvaluator._eval_method_implementation(task, tmp_path)
        assert score > 0.3

    def test_eval_reproducibility(self, tmp_path):
        from minicode.experiments.analyzers.paper_bench_eval import PaperBenchEvaluator

        (tmp_path / "main.py").write_text(
            "import random\nrandom.seed(42)\nimport torch\ntorch.manual_seed(42)\n"
        )

        score = PaperBenchEvaluator._eval_reproducibility(tmp_path)
        assert score >= 0.6

    def test_eval_documentation(self, tmp_path):
        from minicode.experiments.analyzers.paper_bench_eval import PaperBenchEvaluator

        (tmp_path / "README.md").write_text("# Paper Reproduction\n\nThis repository reproduces...\n\n## Setup\n\n```pip install -r requirements.txt```\n\n## Usage\n\n```python main.py```\n")
        (tmp_path / "main.py").write_text(
            '"""Main entry point."""\n\ndef main() -> None:\n    # Run experiment\n    pass\n'
        )

        score = PaperBenchEvaluator._eval_documentation(tmp_path)
        assert score >= 0.5

    def test_compute_summary(self, tmp_path):
        from minicode.experiments.analyzers.paper_bench_eval import (
            PaperBenchEvaluator, PaperBenchResult,
        )

        results = [
            PaperBenchResult(paper_id="p1", score=85.0, max_score=100,
                             rubric_results={"code_structure": 0.8, "method_implementation": 0.9},
                             files_generated=5),
            PaperBenchResult(paper_id="p2", score=60.0, max_score=100,
                             rubric_results={"code_structure": 0.6, "method_implementation": 0.6},
                             files_generated=3),
        ]
        summary = PaperBenchEvaluator().compute_summary(results)
        assert summary["mean_normalized"] == 0.725
        assert summary["total_papers"] == 2
        assert summary["mean_files_generated"] == 4.0

    def test_empty_summary(self):
        from minicode.experiments.analyzers.paper_bench_eval import PaperBenchEvaluator

        summary = PaperBenchEvaluator().compute_summary([])
        assert summary["mean_score"] == 0.0
        assert summary["total_papers"] == 0


class TestAnalyzeResults:
    """Test the analyze_results script functions."""

    def test_welch_ttest_equal(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_results",
            r"d:\Desktop\minicode\py-src\scripts\analyze_results.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        t, p = mod._welch_ttest([0.5, 0.5, 0.5], [0.5, 0.5, 0.5])
        assert abs(t) < 0.001

    def test_welch_ttest_different(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_results",
            r"d:\Desktop\minicode\py-src\scripts\analyze_results.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        t, p = mod._welch_ttest([0.5, 0.5, 0.5], [0.8, 0.8, 0.8])
        assert abs(t) > 1.0

    def test_cohens_d(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_results",
            r"d:\Desktop\minicode\py-src\scripts\analyze_results.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        d = mod._cohens_d([0.5, 0.5, 0.5], [0.8, 0.8, 0.8])
        assert d > 1.0

    def test_cohens_d_small(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_results",
            r"d:\Desktop\minicode\py-src\scripts\analyze_results.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        d = mod._cohens_d([0.5, 0.5, 0.5], [0.55, 0.55, 0.55])
        assert 0 < d < 1.0