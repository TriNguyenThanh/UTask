FROM ghcr.io/astral-sh/uv:0.12.17 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_HTTP_TIMEOUT=600 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.production
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh
RUN useradd --create-home integration && chown -R integration:integration /app
USER integration
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-", "--access-logformat", "%(t)s %(m)s %(U)s status=%(s)s duration=%(L)s request_id=%({x-request-id}i)s"]
