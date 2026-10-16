from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

Message = dict[str, str]


class Sample(BaseModel):
    id: str
    input: str
    target: str
    choices: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateConfig(BaseModel):
    temperature: float = 0.0
    max_tokens: int = 1024
    top_p: float | None = None
    seed: int | None = None
    stop: list[str] | None = None
    timeout: float = 120.0

    def cache_fields(self) -> dict[str, Any]:
        # timeout affects how long we wait, not what the model returns
        return self.model_dump(exclude={"timeout"})


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ModelOutput(BaseModel):
    text: str
    finish_reason: str | None = None
    usage: Usage = Field(default_factory=Usage)
    latency_s: float = 0.0
    cached: bool = False


class Score(BaseModel):
    value: float
    extracted: str | None = None
    method: str | None = None


class Outcome(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    EXTRACT_FAILED = "extract_failed"
    TRUNCATED = "truncated"
    API_ERROR = "api_error"


class SampleResult(BaseModel):
    sample: Sample
    messages: list[Message] = Field(default_factory=list)
    output: ModelOutput | None = None
    score: Score | None = None
    error: str | None = None
    outcome: Outcome | None = None
    attempts: int = 0


def classify(result: SampleResult) -> Outcome:
    if result.error is not None or result.output is None or result.score is None:
        return Outcome.API_ERROR
    if result.score.value >= 1.0:
        return Outcome.CORRECT
    if result.output.finish_reason == "length":
        return Outcome.TRUNCATED
    if result.score.extracted is None:
        return Outcome.EXTRACT_FAILED
    return Outcome.WRONG
