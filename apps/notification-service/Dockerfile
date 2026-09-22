FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "uv run python manage.py migrate --noinput && uv run python manage.py runserver 0.0.0.0:8000"]
