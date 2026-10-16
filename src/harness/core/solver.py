from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from harness.core.fingerprint import fingerprint
from harness.core.types import Message, ModelOutput, Sample

Generate = Callable[[list[Message]], Awaitable[ModelOutput]]


class Solver(Protocol):
    """Decides how a model answers a sample.

    A solver receives a ``generate`` function (already wrapped with caching, retries
    and timeouts by the runner) so that multi-step solvers such as agent loops can
    call the model as many times as they need.
    """

    name: str

    async def __call__(
        self, sample: Sample, generate: Generate
    ) -> tuple[list[Message], ModelOutput]: ...

    def describe(self) -> dict[str, Any]: ...


class PromptSolver:
    """Single-turn solver: optional system prompt, few-shot turns, then the question."""

    name = "prompt"

    def __init__(
        self,
        user_template: Callable[[Sample], str],
        *,
        template_text: str,
        assistant_template: Callable[[Sample], str] | None = None,
        system: str | None = None,
        fewshot: Callable[[Sample], list[Sample]] | None = None,
        fewshot_desc: dict[str, Any] | None = None,
    ) -> None:
        self._user = user_template
        self._assistant = assistant_template
        self._system = system
        self._fewshot = fewshot
        self._template_text = template_text
        self._fewshot_desc = fewshot_desc or {}

    def build_messages(self, sample: Sample) -> list[Message]:
        messages: list[Message] = []
        if self._system:
            messages.append({"role": "system", "content": self._system})
        if self._fewshot is not None:
            if self._assistant is None:
                raise ValueError("few-shot prompting requires an assistant_template")
            for shot in self._fewshot(sample):
                messages.append({"role": "user", "content": self._user(shot)})
                messages.append({"role": "assistant", "content": self._assistant(shot)})
        messages.append({"role": "user", "content": self._user(sample)})
        return messages

    async def __call__(
        self, sample: Sample, generate: Generate
    ) -> tuple[list[Message], ModelOutput]:
        messages = self.build_messages(sample)
        return messages, await generate(messages)

    def describe(self) -> dict[str, Any]:
        desc = {
            "name": self.name,
            "system": self._system,
            "user_template": self._template_text,
            "fewshot": self._fewshot_desc,
        }
        desc["fingerprint"] = fingerprint(desc)
        return desc
