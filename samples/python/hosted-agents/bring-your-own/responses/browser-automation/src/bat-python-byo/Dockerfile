FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PORT=8088

WORKDIR /app

# Install Python dependencies
WORKDIR /app/user_agent
COPY pyproject.toml uv.lock uv.toml ./
# Precompile installed dependencies to reduce startup compilation overhead.
# This covers site-packages, not the stdlib or application source outside it.
# PYTHONDONTWRITEBYTECODE disables automatic .pyc writes on import,
# but Python can still read existing valid .pyc files.
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

# Copy source
COPY main.py ./
COPY utils/ ./utils/
COPY skills/ ./skills/

EXPOSE 8088

CMD ["/app/user_agent/.venv/bin/python", "main.py"]
