from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.analysis.stats import summarize
from harness.core.io import read_json, read_results, write_json, write_results
from harness.core.manifest import now
from harness.core.task import get_task
from harness.core.types import classify


def rescore_run(run_dir: Path) -> dict[str, Any]:
    """Re-apply each task's current scorer to the saved raw outputs, without calling the model.

    Use this after changing extraction or scoring logic.
    """
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = read_json(manifest_path)
    changes: dict[str, Any] = {}

    for entry in manifest["tasks"]:
        name = entry["name"]
        samples_path = run_dir / name / "samples.jsonl"
        if not samples_path.exists():
            continue
        scorer = get_task(name, **entry["params"]).scorer
        results = read_results(samples_path)

        flipped = 0
        for r in results:
            if r.output is None:
                continue
            before = r.score.value if r.score else None
            r.score = scorer(r.sample, r.output.text)
            r.outcome = classify(r)
            flipped += before != r.score.value

        summary = summarize(results)
        write_results(samples_path, results)
        write_json(run_dir / name / "summary.json", summary)

        old_fp = entry["scorer"].get("fingerprint")
        entry["scorer"] = scorer.describe()
        new_fp = entry["scorer"]["fingerprint"]
        entry.setdefault("rescore_history", []).append(
            {"at": now(), "from_fingerprint": old_fp, "to_fingerprint": new_fp}
        )
        before_acc = manifest["results"].get(name, {}).get("accuracy")
        manifest["results"][name] = summary
        changes[name] = {
            "accuracy_before": before_acc,
            "accuracy_after": summary["accuracy"],
            "samples_changed": flipped,
        }

    write_json(manifest_path, manifest)
    return changes
