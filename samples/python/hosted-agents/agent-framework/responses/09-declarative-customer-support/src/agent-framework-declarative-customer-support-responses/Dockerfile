FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

ENV PYTHONNOUSERSITE=1

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
# Precompile installed dependencies to reduce startup compilation overhead.
# This covers site-packages, not the stdlib or application source outside it.
# PYTHONDONTWRITEBYTECODE disables automatic .pyc writes on import,
# but Python can still read existing valid .pyc files.
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

COPY . .

EXPOSE 8088

CMD ["/app/user_agent/.venv/bin/python", "main.py"]
