"""Kiểm tra SDK/I/O concrete không vượt ranh giới application/domain tools."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "src"
FRAMEWORKS = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "httpx",
    "celery",
    "google",
    "jwt",
    "cryptography",
}
ALLOWED = {
    "api": {"fastapi", "starlette"},
    "application": set(),
    "context": set(),
    "workflow": {"google"},
    "models": set(),
}


def framework_violations(source: str, layer: str) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
    return (roots & FRAMEWORKS) - ALLOWED[layer]


@pytest.mark.parametrize("layer", ALLOWED)
def test_concrete_sdk_imports_stay_in_allowed_layers(layer):
    for source in (ROOT / layer).rglob("*.py"):
        assert not framework_violations(source.read_text(), layer), str(source)


@pytest.mark.parametrize(
    "statement,layer,expected",
    [
        ("from sqlalchemy import select", "application", {"sqlalchemy"}),
        ("import httpx", "context", {"httpx"}),
        ("from google.adk import Runner", "api", {"google"}),
        ("import celery", "workflow", {"celery"}),
        ("from google.adk.agents import BaseAgent", "workflow", set()),
    ],
)
def test_framework_check_detects_sdk_boundary_violations(statement, layer, expected):
    assert framework_violations(statement, layer) == expected
