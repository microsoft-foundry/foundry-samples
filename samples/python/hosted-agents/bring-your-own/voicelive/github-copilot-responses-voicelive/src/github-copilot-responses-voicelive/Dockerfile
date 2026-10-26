FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app/user_agent
COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --frozen --no-dev --no-install-project

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

# Precompile dependencies best-effort, but fail the build for invalid
# application Python.
RUN PYTHONDONTWRITEBYTECODE= .venv/bin/python -m compileall -q $(.venv/bin/python -c "import sysconfig as s; print(s.get_paths()['stdlib'], s.get_paths()['purelib'])") || true; \
    PYTHONDONTWRITEBYTECODE= .venv/bin/python -m compileall -q -x '[.]venv' .

CMD ["/app/user_agent/.venv/bin/python", "main.py"]
