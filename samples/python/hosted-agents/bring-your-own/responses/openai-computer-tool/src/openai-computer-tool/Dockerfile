FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

# Install Xvfb virtual framebuffer, Tkinter (for the container Paint canvas),
# scrot/x11-apps for PyAutoGUI + Pillow X11 screenshot capture, without Playwright.
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    python3-tk \
    scrot \
    x11-apps \
    x11-utils \
    procps \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONNOUSERSITE=1 \
    UV_SYSTEM_CERTS=1 \
    DISPLAY=:99 \
    XAUTHORITY=/tmp/.Xauthority \
    PATH="/app/user_agent/.venv/bin:$PATH" \
    PORT=8088

WORKDIR /app/user_agent

# Install Python dependencies
COPY pyproject.toml uv.lock ./
# Precompile installed dependencies to reduce startup compilation overhead.
# This covers site-packages, not the stdlib or application source outside it.
# PYTHONDONTWRITEBYTECODE disables automatic .pyc writes on import,
# but Python can still read existing valid .pyc files.
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

# Copy source
COPY main.py ./
COPY scenarios/ ./scenarios/
COPY utils/ ./utils/

EXPOSE 8088

CMD ["sh", "-c", "if ! pgrep -x Xvfb >/dev/null 2>&1; then Xvfb \"${DISPLAY:-:99}\" -screen 0 1280x800x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 & sleep 1; fi; touch \"${XAUTHORITY:-/tmp/.Xauthority}\" 2>/dev/null || true; exec /app/user_agent/.venv/bin/python /app/user_agent/main.py"]
