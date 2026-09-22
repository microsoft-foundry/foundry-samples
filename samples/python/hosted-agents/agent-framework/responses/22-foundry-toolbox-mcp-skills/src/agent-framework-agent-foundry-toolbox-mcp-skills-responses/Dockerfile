FROM ghcr.io/astral-sh/uv:0.12.6 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app/user_agent

COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

EXPOSE 8088

CMD ["/app/user_agent/.venv/bin/python", "main.py"]
