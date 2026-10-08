FROM ghcr.io/astral-sh/uv:0.12.17 AS uv

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY config ./config
COPY accounts ./accounts
COPY authentication ./authentication
COPY common ./common
COPY messaging ./messaging
COPY manage.py ./manage.py

RUN groupadd --system --gid 10001 django \
    && useradd --system --uid 10001 --gid django --create-home --home-dir /home/django django \
    && chown -R django:django /app

USER django
EXPOSE 8000

CMD ["/app/.venv/bin/gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-", "--access-logformat", "%(m)s %(U)s status=%(s)s duration=%(L)s"]
