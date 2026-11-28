FROM ghcr.io/astral-sh/uv:0.12.17 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_HTTP_TIMEOUT=600 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY config ./config
COPY common ./common
COPY infrastructure ./infrastructure
COPY apps ./apps
COPY manage.py ./manage.py
COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh

RUN groupadd --system --gid 10001 django \
    && useradd --system --uid 10001 --gid django --create-home --home-dir /home/django django \
    && chown -R django:django /app

USER django
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--worker-class", "gthread", "--access-logfile", "-", "--error-logfile", "-", "--access-logformat", "%(t)s %(m)s %(U)s status=%(s)s duration=%(L)s request_id=%({x-request-id}i)s"]
