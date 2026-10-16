from __future__ import annotations

import pytest

from harness.core.scorer import NumberMatchScorer
from harness.core.solver import PromptSolver
from harness.core.task import DatasetSpec, Task
from harness.core.types import Sample


def make_samples(n: int = 6) -> list[Sample]:
    return [Sample(id=f"toy/{i}", input=f"What is {i} + {i}?", target=str(2 * i)) for i in range(n)]


def make_task(samples: list[Sample] | None = None) -> Task:
    samples = samples if samples is not None else make_samples()
    return Task(
        name="toy",
        dataset=DatasetSpec(path="local/toy", split="test"),
        load=lambda: samples,
        solver=PromptSolver(lambda s: s.input, template_text="{input}"),
        scorer=NumberMatchScorer(),
        params={},
    )


def question_number(messages: list[dict[str, str]]) -> int:
    return int(messages[-1]["content"].split()[2])


@pytest.fixture
def toy_task() -> Task:
    return make_task()
