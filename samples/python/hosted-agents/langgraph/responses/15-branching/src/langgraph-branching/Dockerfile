FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app/user_agent
COPY pyproject.toml uv.lock uv.toml ./
# Precompile Python bytecode at build time so cold starts don't pay for it.
# uv compiles site-packages, not the stdlib or application code. Slim base
# images ship little precompiled stdlib bytecode, so those imports may still
# compile on first use.
# PYTHONDONTWRITEBYTECODE blocks bytecode writes, not reads, so precompiled
# .pyc files still benefit images that set it.
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

COPY . .

ENV PATH="/app/user_agent/.venv/bin:$PATH"

EXPOSE 8088

CMD ["python", "main.py"]
