# Agent guide

Read `docs/roadmap.md` first: it records the project's goal, design decisions and the next stages with acceptance criteria.

## Development

```bash
uv sync
uv run pytest -q                                  # offline; uses MockModel and in-memory tasks
uv run ruff check . && uv run ruff format --check .
```

For a real end-to-end check without API keys, run a small model through Ollama:

```bash
ollama pull qwen2.5:0.5b-instruct
uv run harness run -c configs/ollama-smoke.yaml
```

## Conventions

- New benchmarks go in `src/harness/tasks/<name>.py` and register with `@register("<name>")`. Adding a benchmark must not require changes to `core/`.
- Pin every dataset to a HuggingFace revision SHA.
- Keep generation and scoring separate: scorers only see the sample and the raw model output, so `harness rescore` works offline.
- Anything that changes what a model sees or how it is scored must show up in the solver/scorer `describe()` output, so it lands in the run manifest and `harness diff` can detect it.
- Tests must not need network access or API keys.
