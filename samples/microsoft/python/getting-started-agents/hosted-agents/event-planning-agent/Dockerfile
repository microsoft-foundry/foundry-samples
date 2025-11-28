# Builder stage - use slim Python image
FROM python:3.12-slim-bookworm AS builder

# Set working directory
WORKDIR /app

# Install uv manually (following official installation)
ARG UV_VERSION=0.5.11
ENV UV_VERSION=${UV_VERSION}
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1

# Copy uv cache to a predictable location for caching
ENV UV_LINK_MODE=copy

# Install dependencies first (separate layer for better caching)
# Copy only dependency files first for better layer caching
COPY uv.lock pyproject.toml README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy the project source code
COPY . /app

# Sync the project itself (now including the source code)
RUN uv sync --frozen --no-dev

# Temporarily install to resolve confliction
RUN uv pip install --force-reinstall /app/azure_ai_agentserver_agentframework-1.0.0b5-py3-none-any.whl
RUN uv pip install azure-ai-projects==2.0.0b1 agent-framework-core==1.0.0b251111 agent-framework-azure-ai==1.0.0b251111

# Final runtime stage - use slim Python image
FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Install Node.js (required for MCP tools) and uv
ENV UV_VERSION=0.5.11
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the application code
COPY --from=builder /app /app

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Set environment variables
ENV PYTHONUNBUFFERED=1

EXPOSE 8088

# Run the application using uv run (just like locally)
CMD ["uv", "run", "app"]
