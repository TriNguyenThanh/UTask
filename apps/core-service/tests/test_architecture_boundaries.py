"""Architecture fitness tests enforcing Modular Monolith domain boundaries via AST."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

APPS_ROOT = Path(__file__).resolve().parents[1] / "apps"

DOMAIN_APPS = {
    "identity": {"accounts", "authentication"},
    "classroom": {"courses", "groups"},
    "work": {"projects", "sprints", "tasks", "collaboration", "integrations"},
}

APP_TO_DOMAIN = {app: domain for domain, apps in DOMAIN_APPS.items() for app in apps}
ALLOWED_CROSS_DOMAIN_PREFIXES = (
    "apps.accounts.interface",
    "apps.groups.interface",
    "apps.projects.interface",
)


def _iter_imported_modules(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_no_cross_domain_model_or_internal_imports():
    """Bounded contexts (identity, classroom, work) may communicate ONLY via interface.py."""
    violations: list[str] = []
    for app_name, source_domain in APP_TO_DOMAIN.items():
        app_dir = APPS_ROOT / app_name
        if not app_dir.exists():
            continue
        for py_file in app_dir.rglob("*.py"):
            if "migrations" in py_file.parts:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for imported in _iter_imported_modules(tree):
                if not imported.startswith("apps."):
                    continue
                parts = imported.split(".")
                target_app = parts[1] if len(parts) > 1 else ""
                target_domain = APP_TO_DOMAIN.get(target_app)
                if target_domain is None or target_domain == source_domain:
                    continue
                if imported.startswith(ALLOWED_CROSS_DOMAIN_PREFIXES):
                    continue
                rel = py_file.relative_to(APPS_ROOT.parent)
                violations.append(
                    f"{rel} ({source_domain}) illegally imports '{imported}' ({target_domain})"
                )
    assert not violations, "Cross-domain boundary violations:\n" + "\n".join(violations)


def test_common_layer_defines_no_django_models():
    """common/ must stay a pure shared library with zero Django models or migrations."""
    common_root = APPS_ROOT.parent / "common"
    assert not (common_root / "models.py").exists()
    assert not (common_root / "migrations").exists()
    for py_file in common_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ast.unparse(base)
                    assert "models.Model" not in base_name, f"Model found in common: {py_file}"
