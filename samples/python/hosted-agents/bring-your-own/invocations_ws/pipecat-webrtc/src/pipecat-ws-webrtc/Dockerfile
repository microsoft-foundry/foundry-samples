FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# Keep bytecode out of the image layer that pip writes, then precompile
# deliberately below once the app code is in place.
ENV PYTHONDONTWRITEBYTECODE=1

# Foundry hosted agents expose port 8088 by convention; force the
# server to bind there regardless of the .env default (8089).
ENV SERVER_PORT=8088

# Install Python dependencies and strip unnecessary artifacts in the same layer.
COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --frozen --no-dev --no-install-project \
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

# Precompile Python bytecode at build time so cold starts don't pay for it.
# These base images ship almost none of the standard library precompiled
# (~2% of stdlib .py files, on both Debian-slim and Azure Linux), so without
# this every new container recompiles hundreds of stdlib modules on first
# import. Dependencies are best-effort (`|| true`) so a stray unparsable file
# vendored by a third-party package can't fail the build; application code is
# compiled strictly so a syntax error surfaces at build time rather than at
# container start.
# PYTHONDONTWRITEBYTECODE is cleared for these commands only: it blocks
# bytecode *writes*, not *reads*, so images that set it still benefit.
RUN PYTHONDONTWRITEBYTECODE= .venv/bin/python -m compileall -q $(.venv/bin/python -c "import sysconfig as s; print(s.get_paths()['stdlib'], s.get_paths()['purelib'])") || true; \
    PYTHONDONTWRITEBYTECODE= .venv/bin/python -m compileall -q -x '[.]venv' .

CMD ["/app/.venv/bin/python", "server.py"]
