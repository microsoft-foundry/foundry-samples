FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app/user_agent
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Bake the pinned, checksum-verified Copilot runtime into a fixed location so
# containers start without downloading it. Skipping downloads afterwards makes
# a missing runtime fail fast instead of fetching one at request time.
ENV COPILOT_CLI_EXTRACT_DIR=/opt/github-copilot-sdk-runtime
RUN .venv/bin/python -m copilot download-runtime && \
    chmod -R a+rX "$COPILOT_CLI_EXTRACT_DIR"
ENV COPILOT_SKIP_CLI_DOWNLOAD=1

EXPOSE 8088

# Precompile bytecode so cold starts do not recompile the standard library and
# dependencies. Application code is compiled strictly to fail the build early.
RUN PYTHONDONTWRITEBYTECODE= .venv/bin/python -m compileall -q $(.venv/bin/python -c "import sysconfig as s; print(s.get_paths()['stdlib'], s.get_paths()['purelib'])") || true; \
    PYTHONDONTWRITEBYTECODE= .venv/bin/python -m compileall -q -x '[.]venv' .

CMD ["/app/user_agent/.venv/bin/python", "main.py"]
