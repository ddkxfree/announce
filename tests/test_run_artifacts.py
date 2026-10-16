import asyncio
import json

import pytest
from conftest import make_task, question_number

from harness.analysis import rescore as rescore_mod
from harness.analysis.diff import diff_manifests, diff_runs, flatten
from harness.analysis.rescore import rescore_run
from harness.analysis.stats import bootstrap_ci, summarize
from harness.core.io import read_results
from harness.core.model import MockModel
from harness.core.runner import run_eval
from harness.core.scorer import NumberMatchScorer
from harness.core.types import GenerateConfig


def evaluate(tmp_path, respond, config=None):
    return asyncio.run(
        run_eval(
            MockModel(respond, name="mock-model"),
            [(make_task(), config or GenerateConfig())],
            output_dir=tmp_path / "runs",
            run_config={"note": "test"},
        )
    )


def good(m):
    return f"The answer is {2 * question_number(m)}"


def test_run_writes_manifest_summary_and_samples(tmp_path):
    run_dir = evaluate(tmp_path, good)
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert manifest["status"] == "completed"
    assert manifest["model"] == {"type": "mock", "name": "mock-model"}
    env = manifest["environment"]
    assert {"git_commit", "python", "packages", "uv_lock_sha256"} <= env.keys()
    (task,) = manifest["tasks"]
    assert task["n_samples"] == 6
    assert task["solver"]["fingerprint"] and task["scorer"]["fingerprint"]
    assert task["sample_ids_sha256"]
    assert task["generate_config"]["temperature"] == 0.0
    assert manifest["results"]["toy"]["accuracy"] == 1.0

    results = read_results(run_dir / "toy" / "samples.jsonl")
    assert len(results) == 6
    assert results[0].messages[-1]["content"] == "What is 0 + 0?"
    assert json.loads((run_dir / "toy" / "summary.json").read_text())["n"] == 6


def test_manifest_contains_no_api_key(tmp_path, monkeypatch):
    from harness.core.model import get_model

    model = get_model("dashscope/qwen-plus", api_key="sk-secret-value")
    assert "sk-secret-value" not in json.dumps(model.spec())


def test_rescore_uses_saved_outputs(tmp_path, monkeypatch):
    run_dir = evaluate(tmp_path, lambda m: f"I got {2 * question_number(m)} in total")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["results"]["toy"]["accuracy"] == 1.0

    strict = make_task()
    strict.scorer = NumberMatchScorer(fallback_last_number=False)
    monkeypatch.setattr(rescore_mod, "get_task", lambda name, **params: strict)

    changes = rescore_run(run_dir)
    assert changes["toy"]["accuracy_after"] == 0.0
    assert changes["toy"]["samples_changed"] == 6
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["results"]["toy"]["outcomes"]["extract_failed"] == 6
    assert len(manifest["tasks"][0]["rescore_history"]) == 1


def test_diff_reports_config_changes_and_flips(tmp_path):
    a = evaluate(tmp_path, good)

    def worse(m):
        n = question_number(m)
        return "The answer is 99" if n in (1, 2) else good(m)

    b = evaluate(tmp_path, worse, GenerateConfig(temperature=0.7))
    d = diff_runs(a, b)

    keys = {k for k, _, _ in d["manifest_changes"]}
    assert "tasks.toy.generate_config.temperature" in keys
    t = d["tasks"]["toy"]
    assert t["regressions"] == ["toy/1", "toy/2"]
    assert t["improvements"] == []
    assert t["identical_outputs"] == 4
    assert t["outcome_transitions"] == {"correct -> wrong": 2}


def test_identical_runs_have_no_manifest_changes(tmp_path):
    a = evaluate(tmp_path, good)
    b = evaluate(tmp_path, good)
    assert a != b
    assert diff_runs(a, b)["manifest_changes"] == []


def test_flatten_indexes_named_lists():
    assert flatten({"tasks": [{"name": "x", "n": 1}]}) == {"tasks.x.name": "x", "tasks.x.n": 1}


def test_task_missing_from_one_run_is_reported_once():
    a = {"tasks": [{"name": "x", "n": 1}, {"name": "y", "n": 2, "m": 3}]}
    b = {"tasks": [{"name": "x", "n": 5}]}
    assert diff_manifests(a, b) == [("tasks.x.n", 1, 5), ("tasks.y", "<present>", None)]


def test_bootstrap_ci_brackets_mean():
    values = [1.0] * 70 + [0.0] * 30
    lo, hi = bootstrap_ci(values)
    assert lo < 0.7 < hi
    assert hi - lo < 0.25
    assert bootstrap_ci([]) == (0.0, 0.0)


def test_summary_counts_errors_as_failures(tmp_path):
    def respond(m):
        if question_number(m) == 0:
            raise ValueError("x")
        return good(m)

    run_dir = evaluate(tmp_path, respond)
    s = summarize(read_results(run_dir / "toy" / "samples.jsonl"))
    assert s["accuracy"] == pytest.approx(5 / 6)
    assert s["outcomes"]["api_error"] == 1
    assert s["rates"]["api_error"] == pytest.approx(1 / 6)
    assert s["extraction_methods"] == {"answer_is": 5}
