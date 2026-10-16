from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from harness.core.types import Outcome, SampleResult


def bootstrap_ci(
    values: list[float], *, n_boot: int = 1000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = arr[rng.integers(0, len(arr), size=(n_boot, len(arr)))].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def summarize(results: list[SampleResult]) -> dict[str, Any]:
    n = len(results)
    # API errors count as failures: dropping them would inflate accuracy
    values = [r.score.value if r.score else 0.0 for r in results]
    outcomes = Counter(r.outcome.value for r in results if r.outcome)
    methods = Counter((r.score.method or "none") for r in results if r.score)
    outputs = [r.output for r in results if r.output]
    fresh = [o.latency_s for o in outputs if not o.cached]
    lo, hi = bootstrap_ci(values)

    return {
        "n": n,
        "accuracy": sum(values) / n if n else 0.0,
        "ci95": [lo, hi],
        "outcomes": {o.value: outcomes.get(o.value, 0) for o in Outcome},
        "rates": {o.value: (outcomes.get(o.value, 0) / n if n else 0.0) for o in Outcome},
        "extraction_methods": dict(methods.most_common()),
        "tokens": {
            "input": sum(o.usage.input_tokens for o in outputs),
            "output": sum(o.usage.output_tokens for o in outputs),
        },
        "cached": sum(o.cached for o in outputs),
        "mean_latency_s": sum(fresh) / len(fresh) if fresh else None,
    }
