from __future__ import annotations

import re
from typing import Any

from harness.core.scorer import NumberMatchScorer
from harness.core.solver import PromptSolver
from harness.core.task import DatasetSpec, Task, register, select
from harness.core.types import Sample
from harness.tasks._hf import load_rows

REVISION = "740312add88f781978c0658806c59bc2815b9866"

USER_TEMPLATE = (
    "{question}\n\n"
    "Solve the problem step by step. "
    'Finish with a final line of the form "The answer is <number>".'
)


def parse_answer(answer: str) -> tuple[str, str]:
    """Split a GSM8K answer into (reasoning, final number)."""
    reasoning, _, final = answer.rpartition("####")
    reasoning = re.sub(r"<<[^>]*>>", "", reasoning).strip()
    return reasoning, final.strip().replace(",", "")


def row_to_sample(row: dict[str, Any], idx: int, split: str) -> Sample:
    reasoning, final = parse_answer(row["answer"])
    return Sample(
        id=f"gsm8k/{split}/{idx}",
        input=row["question"],
        target=final,
        metadata={"reasoning": reasoning},
    )


def user_prompt(sample: Sample) -> str:
    return USER_TEMPLATE.format(question=sample.input)


def assistant_prompt(sample: Sample) -> str:
    return f"{sample.metadata['reasoning']}\nThe answer is {sample.target}."


@register("gsm8k")
def gsm8k(
    limit: int | None = None,
    seed: int | None = 0,
    n_shot: int = 0,
    split: str = "test",
) -> Task:
    dataset = DatasetSpec(path="openai/gsm8k", config="main", split=split, revision=REVISION)
    fewshot_spec = DatasetSpec(path="openai/gsm8k", config="main", split="train", revision=REVISION)

    def load() -> list[Sample]:
        rows = load_rows(dataset)
        return select([row_to_sample(r, i, split) for i, r in enumerate(rows)], limit, seed)

    shots: list[Sample] = []

    def fewshot(_: Sample) -> list[Sample]:
        if not shots:
            rows = load_rows(fewshot_spec)[:n_shot]
            shots.extend(row_to_sample(r, i, "train") for i, r in enumerate(rows))
        return shots

    solver = PromptSolver(
        user_prompt,
        template_text=USER_TEMPLATE,
        assistant_template=assistant_prompt,
        fewshot=fewshot if n_shot > 0 else None,
        fewshot_desc={"n_shot": n_shot, "source": fewshot_spec.model_dump(), "selection": "first"},
    )
    return Task(
        name="gsm8k",
        dataset=dataset,
        load=load,
        solver=solver,
        scorer=NumberMatchScorer(),
        params={"limit": limit, "seed": seed, "n_shot": n_shot, "split": split},
    )
