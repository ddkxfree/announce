from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from harness.core.scorer import Scorer
from harness.core.solver import Solver
from harness.core.types import Sample


class DatasetSpec(BaseModel):
    path: str
    config: str | None = None
    split: str
    revision: str | None = None


@dataclass
class Task:
    name: str
    dataset: DatasetSpec
    load: Callable[[], list[Sample]]
    solver: Solver
    scorer: Scorer
    params: dict[str, Any] = field(default_factory=dict)


TaskFactory = Callable[..., Task]
TASKS: dict[str, TaskFactory] = {}


def register(name: str) -> Callable[[TaskFactory], TaskFactory]:
    def deco(fn: TaskFactory) -> TaskFactory:
        if name in TASKS:
            raise ValueError(f"Task {name!r} is already registered")
        TASKS[name] = fn
        return fn

    return deco


def get_task(name: str, **params: Any) -> Task:
    import harness.tasks  # noqa: F401  (populates the registry)

    if name not in TASKS:
        raise KeyError(f"Unknown task {name!r}. Known: {', '.join(sorted(TASKS))}")
    return TASKS[name](**params)


def select(samples: list[Sample], limit: int | None, seed: int | None) -> list[Sample]:
    """Pick a deterministic subset. Returned samples keep their original order."""
    if limit is None or limit >= len(samples):
        return samples
    if seed is None:
        return samples[:limit]
    idx = sorted(random.Random(seed).sample(range(len(samples)), limit))
    return [samples[i] for i in idx]
