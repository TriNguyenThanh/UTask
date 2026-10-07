"""Giữ hướng import giữa layer khi bổ sung runtime/adapter về sau."""

import ast
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src"

# main.py là composition root, được phép lắp ghép mọi layer.
ALLOWED_INTERNAL_IMPORTS = {
    "api": {"api", "application", "errors", "models"},
    "application": {"application", "errors", "models"},
    "workflow": {"workflow", "errors", "models"},
    "infrastructure": {"infrastructure", "application", "workflow", "errors", "models"},
    "models": {"models"},
}
INTERNAL_MODULES = {*ALLOWED_INTERNAL_IMPORTS, "main", "config", "errors"}


@pytest.mark.parametrize("layer", ALLOWED_INTERNAL_IMPORTS)
def test_layer_imports_follow_dependency_direction(layer: str) -> None:
    violations = []
    sources = list((PACKAGE_ROOT / layer).rglob("*.py"))
    assert sources, f"Không tìm thấy source của layer {layer}"
    for source in sources:
        relative = source.relative_to(PACKAGE_ROOT).with_suffix("")
        parts = relative.parts[:-1] if source.name == "__init__.py" else relative.parts
        module = ".".join(parts)
        package = module if source.name == "__init__.py" else module.rpartition(".")[0]
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = "." * node.level + (node.module or "")
                imports = [resolve_name(imported, package) if node.level else imported]
            else:
                continue

            for imported in imports:
                dependency = imported.split(".")[0]
                if dependency in INTERNAL_MODULES:
                    if dependency not in ALLOWED_INTERNAL_IMPORTS[layer]:
                        violations.append(f"{source.relative_to(PACKAGE_ROOT)} → {imported}")
                elif layer != "api" and imported.split(".")[0] in {"fastapi", "starlette"}:
                    violations.append(f"{source.relative_to(PACKAGE_ROOT)} → {imported}")

    assert violations == [], "\n".join(violations)


@pytest.mark.parametrize(
    "statement",
    [
        "from infrastructure.providers import UnconfiguredProvider",
        "import infrastructure.repositories",
        "from api import router",
        "from fastapi import FastAPI",
        "from main import create_app",
    ],
)
def test_dependency_check_rejects_forbidden_imports(
    statement: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layer = tmp_path / "application"
    layer.mkdir()
    (layer / "service.py").write_text(statement)
    monkeypatch.setattr(sys.modules[__name__], "PACKAGE_ROOT", tmp_path)

    with pytest.raises(AssertionError, match="service.py →"):
        test_layer_imports_follow_dependency_direction("application")


def test_dependency_check_rejects_missing_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.modules[__name__], "PACKAGE_ROOT", tmp_path)

    with pytest.raises(AssertionError, match="Không tìm thấy source"):
        test_layer_imports_follow_dependency_direction("application")
