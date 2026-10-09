"""Thiết lập mock: cấu hình trong ai-service.env, secret trong .env root."""

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_hex

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values, set_key

from config import ROOT_DIR, Settings


def prepare_mock_environment(
    repo_root: Path,
    token_hours: int = 24,
    *,
    refresh: bool = False,
) -> Path:
    config_path = repo_root / "infra" / "env" / "ai-service.env"
    secret_path = repo_root / ".env"
    tokens_path = repo_root / ".env.mock"
    existing = dotenv_values(secret_path) if secret_path.exists() else {}
    settings = Settings(_env_file=config_path, mock_test=True)
    if not 1 <= token_hours <= 24:
        raise ValueError("Token mock chỉ có thời hạn 1–24 giờ")
    if tokens_path.is_file() or (
        not refresh and (tokens_path.exists() or existing.get("AI_JWT_PUBLIC_KEY"))
    ):
        raise FileExistsError("Đã có credential mock; dùng --refresh để thay JWT có chủ đích")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    secrets = {
        "AI_DB_PASSWORD": existing.get("AI_DB_PASSWORD") or token_hex(16),
        "AI_CREDENTIAL_KEY": existing.get("AI_CREDENTIAL_KEY") or Fernet.generate_key().decode(),
        "AI_JWT_PUBLIC_KEY": public.decode(),
        "GOOGLE_API_KEY": existing.get("GOOGLE_API_KEY") or "",
    }
    now = datetime.now(UTC)
    tokens = {
        user: jwt.encode(
            {
                "sub": user,
                "iat": now,
                "exp": now + timedelta(hours=token_hours),
                "iss": "utask-local-mock",
                "aud": "utask-ai",
            },
            private,
            algorithm="RS256",
        )
        for user in ("mock-owner", "mock-outsider")
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tokens_path.mkdir(mode=0o700, exist_ok=refresh)
    secret_path.touch(mode=0o600, exist_ok=True)
    config_path.touch(exist_ok=True)
    for key, value in secrets.items():
        set_key(secret_path, key, value)
    for key, value in {
        "AI_ENVIRONMENT": settings.environment,
        "MOCK_TEST": "true",
        "AI_JWT_ISSUER": "utask-local-mock",
        "AI_JWT_AUDIENCE": "utask-ai",
        "AI_JWT_ALGORITHM": "RS256",
        "AI_JWT_JWKS_URL": "",
    }.items():
        set_key(config_path, key, value)
    secret_path.chmod(0o600)
    config_path.chmod(0o644)
    for user, token in tokens.items():
        path = tokens_path / f"{user}.jwt"
        path.write_text(token + "\n", encoding="utf-8")
        path.chmod(0o600)
    return secret_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT_DIR)
    parser.add_argument("--token-hours", type=int, default=24)
    parser.add_argument("--refresh", action="store_true", help="Thay JWT, giữ DB/Fernet/LLM key")
    args = parser.parse_args()
    try:
        secret_path = prepare_mock_environment(
            args.repo_root, args.token_hours, refresh=args.refresh
        )
    except (ValueError, OSError):
        parser.exit(1, "Không tạo được mock; kiểm tra cấu hình và --refresh nếu đã có JWT.\n")
    print(f"Đã cập nhật cấu hình; secret ở {secret_path}, JWT ở {args.repo_root / '.env.mock'}.")


if __name__ == "__main__":
    main()
