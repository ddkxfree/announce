import asyncio

import pytest

pytest.importorskip("swebench")

from harness.core.task import get_task  # noqa: E402
from harness.sandbox.base import ExecResult, Sandbox, SandboxError  # noqa: E402
from harness.tasks.swebench import apply_patch, collect_patch  # noqa: E402

PATCH = "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-x\n+y\n"


class GitSandbox(Sandbox):
    """Records commands; ``results`` maps a command substring to its result."""

    def __init__(self, results: dict[str, ExecResult] | None = None) -> None:
        self.results = results or {}
        self.commands: list[str] = []
        self.files: dict[str, bytes] = {}

    async def exec(self, cmd: str, *, timeout: float = 60.0) -> ExecResult:
        self.commands.append(cmd)
        for key, res in self.results.items():
            if key in cmd:
                return res
        return ExecResult(exit_code=0, stdout="", stderr="")

    async def write_file(self, path: str, content: bytes | str) -> None:
        self.files[path] = content.encode() if isinstance(content, str) else content

    async def read_file(self, path: str) -> bytes:
        return self.files[path]

    async def close(self) -> None:
        pass


def test_submitted_diff_is_used_as_is():
    sb = GitSandbox()
    patch, source = asyncio.run(collect_patch(sb, "\n" + PATCH))
    assert (patch, source) == ("\n" + PATCH, "submission")
    assert sb.commands == []


def test_without_a_diff_the_working_tree_is_collected():
    sb = GitSandbox({"diff --cached": ExecResult(exit_code=0, stdout=PATCH, stderr="")})
    patch, source = asyncio.run(collect_patch(sb, "I fixed it."))
    assert (patch, source) == (PATCH, "git_diff")
    assert "git add -A" in sb.commands[0] and "cd /testbed" in sb.commands[0]


def test_git_failure_is_an_environment_error():
    sb = GitSandbox({"diff --cached": ExecResult(exit_code=128, stdout="", stderr="not a repo")})
    with pytest.raises(SandboxError, match="not a repo"):
        asyncio.run(collect_patch(sb, ""))


def test_apply_resets_first_and_falls_back_to_patch():
    fail = ExecResult(exit_code=1, stdout="", stderr="does not apply")
    sb = GitSandbox({"git apply": fail})
    applied, log = asyncio.run(apply_patch(sb, PATCH.rstrip("\n")))

    assert applied
    assert "git reset -q --hard HEAD" in sb.commands[0]
    assert sb.files["/tmp/model.patch"].endswith(b"\n")
    assert any("patch --batch --fuzz=5" in c for c in sb.commands)
    assert "patch --batch" in log


def test_patch_that_never_applies_is_reported():
    fail = ExecResult(exit_code=1, stdout="", stderr="does not apply")
    sb = GitSandbox({"git apply": fail, "patch --batch": fail})
    applied, log = asyncio.run(apply_patch(sb, PATCH))
    assert not applied and log.count("does not apply") == 3


def test_task_factory_validates_solver_and_configures_sandbox():
    with pytest.raises(ValueError, match="unknown solver"):
        get_task("swebench", solver="nope")
    task = get_task("swebench", solver="oracle", ids=["django__django-11099"])
    assert task.dataset.revision and task.scorer.requires_sandbox
    from harness.core.types import Sample

    spec = task.sandbox(Sample(id="x", input="", target="", metadata={"image": "img"}))
    assert (spec.image, spec.workdir, spec.network) == ("img", "/testbed", True)
    assert get_task("swebench", solver="agent").solver.system_prompt.count("/testbed") == 1
