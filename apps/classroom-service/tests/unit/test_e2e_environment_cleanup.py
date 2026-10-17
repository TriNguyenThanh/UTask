"""Lifecycle failure paths with Docker doubles; real cleanup runs after the E2E suite."""

import subprocess
from types import SimpleNamespace

import pytest

from tests.e2e.docker_environment import DockerEnvironment

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure_stage", ["setup", "test"])
def test_lifecycle_failure_removes_only_owned_stack_resources(tmp_path, monkeypatch, failure_stage):
    stack = DockerEnvironment("utask", "ci", tmp_path)
    commands = []

    def docker(*args, **kwargs):
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    def partial_start():
        stack.config.write_text("{}", encoding="utf-8")
        if failure_stage == "setup":
            raise RuntimeError("injected setup failure")

    monkeypatch.setattr(stack, "docker", docker)
    monkeypatch.setattr(stack, "start", partial_start)

    with pytest.raises(RuntimeError, match=f"injected {failure_stage} failure"), stack:
        raise RuntimeError("injected test failure")

    assert not stack.directory.exists()
    compose = [args for args in commands if args[0] == "compose"]
    assert len(compose) == 2
    assert all(args[1:5] == ("-p", stack.project, "-f", str(stack.config)) for args in compose)
    assert compose[-1][5:] == ("down", "--volumes", "--remove-orphans")
    assert {args for args in commands if args[0] != "compose"} == {
        (kind, "ls", "--filter", f"label=com.docker.compose.project={stack.project}", "-q")
        for kind in ("container", "volume", "network")
    }


def test_startup_uses_broker_health_topic_preparation_before_migrations(tmp_path, monkeypatch):
    stack = DockerEnvironment("utask", "ci", tmp_path)
    commands = []

    def compose(*args):
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="127.0.0.1:18080\n", stderr="")

    monkeypatch.setattr(stack, "configure", lambda: None)
    monkeypatch.setattr(stack, "compose", compose)
    monkeypatch.setattr(
        "tests.e2e.docker_environment.requests.get",
        lambda *args, **kwargs: SimpleNamespace(json=lambda: {"status": "ok"}),
    )
    try:
        stack.start()
    finally:
        stack.temporary.cleanup()

    assert commands[0][-3:] == ("postgres", "redis", "kafka")
    assert "--wait" in commands[0]
    migrations = [command for command in commands if command[0] == "run"]
    assert [command[3] for command in migrations] == [
        "identity-service",
        "classroom-service",
        "work-service",
    ]
    assert all(command[-2:] == ("migrate", "--noinput") for command in migrations)
    assert not any("create_topics" in str(command) for command in commands)
    assert stack.gateway == "http://127.0.0.1:18080"
