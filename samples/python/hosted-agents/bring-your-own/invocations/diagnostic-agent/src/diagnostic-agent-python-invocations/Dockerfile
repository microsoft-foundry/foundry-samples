FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim

ENV PYTHONNOUSERSITE=1

COPY --from=uv /uv /uvx /bin/

# Network diagnostic CLIs that may be used by probes when exec'ing into the sandbox VM.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dnsutils \
        inetutils-telnet \
        iproute2 \
        iputils-arping \
        iputils-ping \
        iputils-tracepath \
        mtr-tiny \
        net-tools \
        openssl \
        tcpdump \
        tcptraceroute \
        traceroute \
        tshark \
        wget \
    && rm -rf /var/lib/apt/lists/*

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
