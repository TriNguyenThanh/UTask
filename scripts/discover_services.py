"""Discover Python services and derive CI/release matrices from source and Compose."""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

import yaml


def read_python_services(root: Path, compose: dict):
    """Read runnable app manifests, without loading any service dependencies."""
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
        if runtime.get("profiles", []) not in ([], [directory.name]):
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
    if not services:
        raise ValueError("No runnable Python services found")
    return services


def validate_runtime(compose: dict, services: dict):
    """Validate active Compose dependencies and declared runtime responsibilities."""

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

    def require_healthcheck(name, runtime):
        healthcheck = runtime.get("healthcheck", {})
        test = healthcheck.get("test") if isinstance(healthcheck, dict) else None
        enabled = isinstance(test, str) and bool(test.strip())
        if isinstance(test, list):
            enabled = (
                len(test) > 1
                and test[0] in ("CMD", "CMD-SHELL")
                and all(isinstance(argument, str) for argument in test)
                and bool(test[1].strip())
            )
        if (
            not isinstance(healthcheck, dict)
            or not enabled
            or healthcheck.get("disable")
        ):
            raise ValueError(f"{name} requires an enabled Compose healthcheck")

    active = {
        name
        for name, runtime in compose.items()
        if not runtime.get("profiles")
        or set(runtime["profiles"]).intersection(services)
    }
    for name in tuple(active):
        active.update(dependencies(name))
    infrastructure_services = []
    gateways = []
    for name in sorted(active):
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise ValueError(f"Invalid Compose service name: {name}")
        runtime = compose[name]
        require_healthcheck(name, runtime)
        if name in services:
            continue
        role = runtime.get("x-deploy", {}).get("role")
        if role == "infrastructure":
            infrastructure_services.append(name)
        elif role == "gateway":
            gateways.append(name)
        elif role == "worker":
            application = runtime["x-deploy"].get("application")
            if application not in services or runtime.get("image") != compose[
                application
            ].get("image"):
                raise ValueError(
                    f"{name}: worker must use the image of a discovered application"
                )
        else:
            raise ValueError(
                f"{name}: declare x-deploy.role (infrastructure, gateway or worker)"
            )
    if len(gateways) != 1:
        raise ValueError("Staging requires exactly one active gateway")
    return (
        infrastructure_services,
        gateways[0],
        {name: dependencies(name) for name in services},
    )


def discover_services(root: Path, changed_files=(), *, shared=False, deployment=False):
    compose = yaml.safe_load(
        (root / "docker-compose.staging.yml").read_text(encoding="utf-8")
    )["services"]
    services = read_python_services(root, compose)
    infrastructure_services, gateway, dependencies = validate_runtime(compose, services)

    checks, release_services, django_services, gateway_health_paths = [], [], [], []
    release_needed = False
    for name, service in services.items():
        runtime = service["runtime"]
        post_deploy = runtime.get("x-deploy", {})
        if (
            not isinstance(post_deploy, dict)
            or "gateway_health_path" not in post_deploy
        ):
            raise ValueError(
                f"{name}: declare x-deploy.gateway_health_path (null for internal services)"
            )
        health_path = post_deploy["gateway_health_path"]
        if health_path is not None:
            if (
                not isinstance(health_path, str)
                or not re.fullmatch(r"/[A-Za-z0-9._/-]+", health_path)
                or health_path.startswith("//")
            ):
                raise ValueError(
                    f"{name}: gateway_health_path must be an absolute HTTP path"
                )
            if health_path in gateway_health_paths:
                raise ValueError(f"Duplicate gateway_health_path: {health_path}")
            gateway_health_paths.append(health_path)
        deps = dependencies[name]
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
        release_needed = release_needed or changed
        if shared or changed:
            checks.append(
                {
                    "service": name,
                    "postgres": "postgres" in deps,
                    "redis": "redis" in deps,
                    "test_env": json.dumps(test_env),
                }
            )
        release_services.append({"service": name})
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
        "release_matrix": {"include": release_services},
        "release_needed": release_needed,
        "django_services": django_services,
        "gateway_health_paths": gateway_health_paths,
        "infrastructure_services": infrastructure_services,
        "gateway_service": gateway,
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
