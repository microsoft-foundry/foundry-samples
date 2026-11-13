FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1

# Foundry hosted agents expose port 8088 by convention; force the
# server to bind there regardless of the .env default (8089).
ENV PORT=8088

# Install Python dependencies and strip unnecessary artifacts in the same layer.
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

# Copy application code. bot_websocket_server.py and the azure_* helpers are
# shared with the sibling pipecat-ws-server sample and are bundled here so
# the container is self-contained (the runtime sys.path insertion in
# bot_webrtc_server.py is harmless when these files live next to it).
COPY server.py \
     bot_webrtc_server.py \
     bot_websocket_server.py \
     azure_fast_transcription_stt.py \
     azure_tts_text_streaming.py \
     ./

EXPOSE 8088

CMD ["/app/.venv/bin/python", "server.py"]
