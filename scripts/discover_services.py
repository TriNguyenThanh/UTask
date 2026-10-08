"""Discover Python services and derive CI/release matrices from source and Compose."""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

import yaml


def discover_services(root: Path, changed_files=(), *, shared=False, deployment=False):
    compose = yaml.safe_load(
        (root / "docker-compose.staging.yml").read_text(encoding="utf-8")
    )["services"]
    services = {}
    required = ("pyproject.toml", "uv.lock", "Dockerfile")
    for directory in sorted((root / "apps").iterdir()):
        if not directory.is_dir() or directory.name == "web":
            continue
        present = [
            filename for filename in required if (directory / filename).is_file()
        ]
        if not present:
            continue  # README-only scaffolding has no runnable service.
        missing = sorted(set(required) - set(present))
        if missing:
            raise ValueError(f"{directory.name} is missing {', '.join(missing)}")
        if not re.fullmatch(r"[a-z][a-z0-9-]*-service", directory.name):
            raise ValueError(f"Invalid service directory: {directory.name}")
        if directory.name not in compose:
            raise ValueError(f"{directory.name} has no staging Compose service")
        runtime = compose[directory.name]
        if directory.name != "identity-service" and runtime.get("profiles") != [
            directory.name
        ]:
            raise ValueError(f"{directory.name} requires its own Compose profile")
        project = tomllib.loads(
            (directory / "pyproject.toml").read_text(encoding="utf-8")
        )
        services[directory.name] = {
            "runtime": runtime,
            "django": any(
                re.match(r"django(?:[\[<>=!~; ]|$)", dependency, re.IGNORECASE)
                for dependency in project.get("project", {}).get("dependencies", [])
            ),
        }
    if "identity-service" not in services:
        raise ValueError("Identity must have complete source for the staging gateway")

    def dependencies(name, visiting=()):
        if name in visiting:
            raise ValueError(f"Dependency cycle involving {name}")
        if name not in compose:
            raise ValueError(f"Missing Compose dependency: {name}")
        result = set()
        for dependency in compose[name].get("depends_on", {}):
            if dependency.endswith("-service") and dependency not in services:
                raise ValueError(f"{name} requires unimplemented service {dependency}")
            result.add(dependency)
            result.update(dependencies(dependency, (*visiting, name)))
        return result

    checks, release, django_services = [], [], []
    for name, service in services.items():
        deps = dependencies(name)
        test_env = {}
        if "postgres" in deps:
            test_env.update(
                POSTGRES_HOST="127.0.0.1",
                POSTGRES_PORT="5432",
                POSTGRES_USER="utask_ci",
                POSTGRES_PASSWORD="ci-only-postgres-password",
                DATABASE_NAME="ci",
            )
        if "redis" in deps:
            test_env["REDIS_URL"] = "redis://127.0.0.1:6379/15"
        overrides = service["runtime"].get("x-ci", {}).get("test_env", {})
        if not isinstance(overrides, dict) or any(
            not isinstance(value, str) for value in overrides.values()
        ):
            raise ValueError(f"{name}: x-ci.test_env must contain string values")
        test_env.update(overrides)
        code_changed = any(path.startswith(f"apps/{name}/") for path in changed_files)
        changed = code_changed or deployment
        if shared or changed:
            checks.append(
                {
                    "service": name,
                    "postgres": "postgres" in deps,
                    "redis": "redis" in deps,
                    "test_env": json.dumps(test_env),
                }
            )
        release.append({"service": name, "changed": changed})
        if service["django"]:
            django_services.append(name)
    web = root / "apps/web"
    if web.exists() and not all(
        (web / filename).is_file() for filename in ("package.json", "pnpm-lock.yaml")
    ):
        raise ValueError("Web exists but is missing its package manifest or lockfile")
    return {
        "services": list(services),
        "checks": {"include": checks},
        "checks_needed": bool(checks),
        "release_matrix": {"include": release},
        "release_needed": any(item["changed"] for item in release),
        "django_services": django_services,
        "web_ready": web.exists(),
    }


def main():
    result = discover_services(
        Path(__file__).resolve().parents[1],
        json.loads(os.environ.get("CHANGED_FILES", "[]")),
        shared=os.environ.get("SHARED_CHANGED") == "true",
        deployment=os.environ.get("DEPLOYMENT_CHANGED") == "true",
    )
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a") as file:
            file.writelines(
                f"{name}={json.dumps(value)}\n" for name, value in result.items()
            )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
