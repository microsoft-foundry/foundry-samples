FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock uv.toml ./
# Precompile installed dependencies to reduce startup compilation overhead.
# This covers site-packages, not the stdlib or application source outside it.
# PYTHONDONTWRITEBYTECODE disables automatic .pyc writes on import,
# but Python can still read existing valid .pyc files.
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode \
    && (find /app/.venv/lib/python3.12/site-packages \
        \( -type d -name 'tests' \
        -o -type d -name 'test' \) \
        -exec rm -rf {} + 2>/dev/null || true)

# Pre-fetch Silero VAD weights so the agent doesn't download them at
# every cold-start.
RUN .venv/bin/python -c "from livekit.plugins.silero import VAD; VAD.load()"

COPY agent.py server.py azure_tts_text_streaming.py ./

EXPOSE 8088

# server.py spawns `agent.py start` as a child process, so a single
# command runs both the FastAPI signaling endpoint and the LiveKit
# agent worker.

CMD ["/app/.venv/bin/python", "server.py"]
