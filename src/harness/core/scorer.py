from __future__ import annotations

import math
import re
from typing import Any, Protocol

from harness.core.fingerprint import fingerprint
from harness.core.types import Sample, Score

_NUM = r"-?[\d,]*\.?\d+"


class Scorer(Protocol):
    name: str

    def __call__(self, sample: Sample, text: str) -> Score: ...

    def describe(self) -> dict[str, Any]: ...


def normalize_number(raw: str) -> str | None:
    s = raw.strip().replace(",", "").replace("$", "").rstrip(".")
    try:
        value = float(s)
    except ValueError:
        return None
    if math.isfinite(value) and value == int(value):
        return str(int(value))
    return repr(value)


class NumberMatchScorer:
    """Extracts a final numeric answer and compares it to the target.

    Rules are tried in order; the name of the rule that matched is recorded so that
    a run can report how often the model followed the requested answer format.
    """

    name = "number_match"

    RULES: list[tuple[str, str]] = [
        ("answer_is", rf"answer is[:\s]*\**\s*\$?\s*({_NUM})"),
        ("hash_marker", rf"####\s*\$?\s*({_NUM})"),
        ("boxed", rf"\\boxed\{{\s*\$?\s*({_NUM})\s*\}}"),
    ]

    def __init__(self, *, fallback_last_number: bool = True) -> None:
        self.fallback_last_number = fallback_last_number

    def extract(self, text: str) -> tuple[str | None, str | None]:
        for rule, pattern in self.RULES:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            for m in reversed(matches):
                if (value := normalize_number(m)) is not None:
                    return value, rule
        if self.fallback_last_number:
            for m in reversed(re.findall(_NUM, text)):
                if (value := normalize_number(m)) is not None:
                    return value, "last_number"
        return None, None

    def __call__(self, sample: Sample, text: str) -> Score:
        extracted, method = self.extract(text)
        target = normalize_number(sample.target)
        correct = extracted is not None and target is not None and extracted == target
        return Score(value=float(correct), extracted=extracted, method=method)

    def describe(self) -> dict[str, Any]:
        desc = {
            "name": self.name,
            "rules": self.RULES,
            "fallback_last_number": self.fallback_last_number,
        }
        desc["fingerprint"] = fingerprint(desc)
        return desc


class ChoiceScorer:
    """Extracts a multiple-choice letter (A, B, C, ...) and compares it to the target."""

    name = "choice"

    def __init__(self, letters: str = "ABCD", *, fallback_last_letter: bool = True) -> None:
        self.letters = letters
        self.fallback_last_letter = fallback_last_letter
        cls = f"[{letters}]"
        self.rules: list[tuple[str, str]] = [
            # only the phrase is case-insensitive, so "the answer is a bit..." is not "A"
            ("answer_is", rf"(?i:answer is)[:\s]*\**\s*\(?({cls})\b"),
            ("only_letter", rf"^\s*\(?({cls})\)?\s*\.?\s*$"),
            ("leading_letter", rf"^\s*\(?({cls})[\)\.:]"),
        ]

    def extract(self, text: str) -> tuple[str | None, str | None]:
        for rule, pattern in self.rules:
            matches = re.findall(pattern, text)
            if matches:
                return matches[-1], rule
        if self.fallback_last_letter:
            matches = re.findall(rf"\b([{self.letters}])\b", text)
            if matches:
                return matches[-1], "last_letter"
        return None, None

    def __call__(self, sample: Sample, text: str) -> Score:
        extracted, method = self.extract(text)
        correct = extracted is not None and extracted == sample.target.strip().upper()
        return Score(value=float(correct), extracted=extracted, method=method)

    def describe(self) -> dict[str, Any]:
        desc = {
            "name": self.name,
            "letters": self.letters,
            "rules": self.rules,
            "fallback_last_letter": self.fallback_last_letter,
        }
        desc["fingerprint"] = fingerprint(desc)
        return desc
