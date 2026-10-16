from __future__ import annotations

from typing import Any

from harness.core.task import DatasetSpec


def load_rows(spec: DatasetSpec) -> list[dict[str, Any]]:
    from datasets import load_dataset

    ds = load_dataset(spec.path, spec.config, split=spec.split, revision=spec.revision)
    return [dict(row) for row in ds]
