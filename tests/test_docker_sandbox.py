"""Integration tests against a real Docker daemon. Skipped when Docker is unavailable."""

import asyncio

import pytest

from harness.core.model import get_model
from harness.core.runner import run_samples
from harness.core.task import get_task
from harness.core.types import GenerateConfig, Outcome
from harness.sandbox.base import SandboxError, SandboxSpec


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker is not available")

IMAGE = "python:3.12-slim"


def test_exec_files_timeout_and_isolation():
    from harness.sandbox.docker import DockerProvider

    async def scenario():
        provider = DockerProvider()
        sb = await provider.create(SandboxSpec(image=IMAGE), labels={"harness.test": "1"})
        try:
            res = await sb.exec("echo out; echo err >&2; exit 3")
            assert (res.exit_code, res.stdout, res.stderr) == (3, "out\n", "err\n")

            await sb.write_file("sub/dir/f.txt", "content")
            assert await sb.read_file("/app/sub/dir/f.txt") == b"content"
            assert (await sb.exec("cat sub/dir/f.txt")).stdout == "content"
            with pytest.raises(FileNotFoundError):
                await sb.read_file("/nope")

            slow = await sb.exec("sleep 10", timeout=1)
            assert slow.timed_out

            net = await sb.exec(
                "python -c \"import socket; socket.create_connection(('1.1.1.1', 53), 2)\""
            )
            assert net.exit_code != 0
        finally:
            await sb.close()
        containers = provider.client.containers.list(all=True, filters={"label": "harness.test"})
        assert containers == []

    asyncio.run(scenario())


def test_missing_image_is_sandbox_error():
    from harness.sandbox.docker import DockerProvider

    async def scenario():
        await DockerProvider().create(SandboxSpec(image="harness-does-not-exist:never"), labels={})

    with pytest.raises(SandboxError):
        asyncio.run(scenario())


def test_oracle_solves_every_builtin_terminal_task():
    from harness.sandbox.docker import DockerProvider

    task = get_task("terminal", solver="oracle")
    results = asyncio.run(
        run_samples(
            task,
            task.load(),
            get_model("none/none"),
            GenerateConfig(),
            sandbox_provider=DockerProvider(),
        )
    )
    assert [r.outcome for r in results] == [Outcome.CORRECT] * len(results), [
        (r.sample.id, r.error, r.score) for r in results
    ]


def test_untouched_environment_fails_every_builtin_terminal_task():
    """Guards against tests that pass without the agent doing anything."""
    from fakes import scripted

    from harness.sandbox.docker import DockerProvider

    task = get_task("terminal")
    results = asyncio.run(
        run_samples(
            task,
            task.load(),
            scripted("I am done."),
            GenerateConfig(),
            sandbox_provider=DockerProvider(),
        )
    )
    assert [r.outcome for r in results] == [Outcome.WRONG] * len(results)
