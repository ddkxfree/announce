from __future__ import annotations

from typing import Any

from harness.core.scorer import ChoiceScorer
from harness.core.solver import PromptSolver
from harness.core.task import DatasetSpec, Task, register, select
from harness.core.types import Sample
from harness.tasks._hf import load_rows

REVISION = "c30699e8356da336a370243923dbaf21066bb9fe"
LETTERS = "ABCD"

USER_TEMPLATE = (
    "The following is a multiple choice question about {subject}.\n\n"
    "{question}\n{options}\n\n"
    'Reply with the letter of the correct option in the form "The answer is X".'
)


def row_to_sample(row: dict[str, Any], idx: int, split: str) -> Sample:
    return Sample(
        id=f"mmlu/{split}/{idx}",
        input=row["question"],
        target=LETTERS[row["answer"]],
        choices=list(row["choices"]),
        metadata={"subject": row["subject"]},
    )


def user_prompt(sample: Sample) -> str:
    options = "\n".join(f"{LETTERS[i]}. {c}" for i, c in enumerate(sample.choices or []))
    subject = sample.metadata["subject"].replace("_", " ")
    return USER_TEMPLATE.format(subject=subject, question=sample.input, options=options)


def assistant_prompt(sample: Sample) -> str:
    return f"The answer is {sample.target}."


@register("mmlu")
def mmlu(
    limit: int | None = None,
    seed: int | None = 0,
    n_shot: int = 0,
    subjects: list[str] | None = None,
    split: str = "test",
) -> Task:
    dataset = DatasetSpec(path="cais/mmlu", config="all", split=split, revision=REVISION)
    fewshot_spec = DatasetSpec(path="cais/mmlu", config="all", split="dev", revision=REVISION)

    def load() -> list[Sample]:
        samples = [row_to_sample(r, i, split) for i, r in enumerate(load_rows(dataset))]
        if subjects:
            samples = [s for s in samples if s.metadata["subject"] in subjects]
        # rows are grouped by subject, so an unseeded prefix would cover one subject only
        return select(samples, limit, seed)

    by_subject: dict[str, list[Sample]] = {}

    def fewshot(sample: Sample) -> list[Sample]:
        if not by_subject:
            for i, r in enumerate(load_rows(fewshot_spec)):
                by_subject.setdefault(r["subject"], []).append(row_to_sample(r, i, "dev"))
        return by_subject.get(sample.metadata["subject"], [])[:n_shot]

    solver = PromptSolver(
        user_prompt,
        template_text=USER_TEMPLATE,
        assistant_template=assistant_prompt,
        fewshot=fewshot if n_shot > 0 else None,
        fewshot_desc={
            "n_shot": n_shot,
            "source": fewshot_spec.model_dump(),
            "selection": "first_per_subject",
        },
    )
    return Task(
        name="mmlu",
        dataset=dataset,
        load=load,
        solver=solver,
        scorer=ChoiceScorer(LETTERS),
        params={
            "limit": limit,
            "seed": seed,
            "n_shot": n_shot,
            "subjects": subjects,
            "split": split,
        },
    )
