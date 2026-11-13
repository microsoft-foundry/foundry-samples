FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app/user_agent
COPY pyproject.toml uv.lock uv.toml ./
# Precompile installed dependencies to reduce startup compilation overhead.
# This covers site-packages, not the stdlib or application source outside it.
# PYTHONDONTWRITEBYTECODE disables automatic .pyc writes on import,
# but Python can still read existing valid .pyc files.
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

# Resolve the SDK's pinned CLI runtime at build time instead of on the first
# invocation, when the container filesystem may be read-only.
RUN .venv/bin/python -m copilot download-runtime && \
    cli_path="$(find /root/.cache/github-copilot-sdk/cli -type f -name copilot -print -quit)" && \
    test -n "$cli_path" && \
    install -m 0755 "$cli_path" /usr/local/bin/copilot && \
    rm -rf /root/.cache/github-copilot-sdk

ENV COPILOT_CLI_PATH=/usr/local/bin/copilot
ENV PORT=8088
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

COPY . .

EXPOSE 8088

CMD ["/app/user_agent/.venv/bin/python", "main.py"]
