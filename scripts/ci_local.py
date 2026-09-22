"""Run the repository CI checks locally before pushing to the remote."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COREPACK = "corepack.cmd" if os.name == "nt" else "corepack"
PYTHON_SERVICES = (
    "identity-service",
    "work-service",
    "classroom-service",
    "integration-service",
    "notification-service",
    "ai-service",
)


def run(
    label: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    """Run one CI step and stop at the first failure."""

    printable = " ".join(command)
    print(f"\n[local-ci] {label}\n           {printable}", flush=True)
    try:
        result = subprocess.run(command, cwd=cwd, env=env, check=False)
    except FileNotFoundError as error:
        raise SystemExit(f"[local-ci] Missing command: {command[0]}") from error
    if result.returncode:
        raise SystemExit(f"[local-ci] FAILED ({result.returncode}): {label}")


def require_commands(commands: list[str]) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise SystemExit(f"[local-ci] Missing required commands: {', '.join(missing)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run UTask's local equivalent of the GitHub Actions CI checks."
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip Docker image builds after code and configuration checks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_commands(["docker", "uv", COREPACK, "sh"])

    ci_env = os.environ.copy()
    ci_env.update(
        {
            "DJANGO_SECRET_KEY": "ci-only-not-a-production-secret",
            "DJANGO_DEBUG": "false",
            "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1,testserver",
        }
    )

    run(
        "Validate Docker Compose configuration",
        ["docker", "compose", "--env-file", ".env.example", "config", "--quiet"],
    )
    run(
        "Validate PostgreSQL initialization script",
        ["sh", "-n", "infra/postgres/init-databases.sh"],
    )
    nginx_config = ROOT / "infra" / "nginx" / "nginx.conf"
    run(
        "Validate Nginx configuration",
        [
            "docker",
            "run",
            "--rm",
            "--add-host",
            "identity-service:127.0.0.1",
            "--add-host",
            "work-service:127.0.0.1",
            "--add-host",
            "classroom-service:127.0.0.1",
            "--add-host",
            "integration-service:127.0.0.1",
            "--add-host",
            "notification-service:127.0.0.1",
            "--add-host",
            "ai-service:127.0.0.1",
            "--mount",
            f"type=bind,source={nginx_config},target=/etc/nginx/nginx.conf,readonly",
            "nginx:1.27-alpine",
            "nginx",
            "-t",
        ],
    )

    for service in PYTHON_SERVICES:
        service_dir = ROOT / "apps" / service
        run(
            f"Install locked dependencies for {service}",
            ["uv", "sync", "--all-groups", "--locked"],
            cwd=service_dir,
            env=ci_env,
        )
        run(
            f"Ruff lint for {service}",
            ["uv", "run", "ruff", "check", "."],
            cwd=service_dir,
            env=ci_env,
        )
        run(
            f"Ruff format check for {service}",
            ["uv", "run", "ruff", "format", "--check", "."],
            cwd=service_dir,
            env=ci_env,
        )
        run(
            f"Pytest for {service}",
            ["uv", "run", "pytest"],
            cwd=service_dir,
            env=ci_env,
        )

    web_dir = ROOT / "apps" / "web"
    run(
        "Install locked Web dependencies",
        [COREPACK, "pnpm", "install", "--frozen-lockfile"],
        cwd=web_dir,
    )
    run("Web lint", [COREPACK, "pnpm", "lint"], cwd=web_dir)
    run("Web typecheck", [COREPACK, "pnpm", "typecheck"], cwd=web_dir)
    run("Web tests", [COREPACK, "pnpm", "test"], cwd=web_dir)
    run("Web production build", [COREPACK, "pnpm", "build"], cwd=web_dir)

    if args.skip_images:
        print("\n[local-ci] Docker image builds skipped.", flush=True)
    else:
        for service in PYTHON_SERVICES:
            run(
                f"Build Docker image for {service}",
                [
                    "docker",
                    "build",
                    "--tag",
                    f"utask/{service}:ci-local",
                    f"apps/{service}",
                ],
            )

    print("\n[local-ci] All checks passed.", flush=True)


if __name__ == "__main__":
    main()
