FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# .NET 10 runtime is required by the `powerfx` package, which
# agent-framework-declarative uses to evaluate `=...` expressions in the
# workflow YAML (e.g. =Local.Triage.NeedsClarification). Without it,
# ConditionGroup evaluation raises and the workflow produces no output.
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates libicu-dev \
    && wget -qO /tmp/dotnet-install.sh https://dot.net/v1/dotnet-install.sh \
    && chmod +x /tmp/dotnet-install.sh \
    && /tmp/dotnet-install.sh --runtime dotnet --channel 10.0 --install-dir /usr/share/dotnet \
    && ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet \
    && rm -f /tmp/dotnet-install.sh \
    && rm -rf /var/lib/apt/lists/*

ENV DOTNET_ROOT=/usr/share/dotnet

WORKDIR /app/user_agent
COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

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

CMD ["/app/user_agent/.venv/bin/python", "main.py"]
