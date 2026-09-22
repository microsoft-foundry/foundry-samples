FROM ghcr.io/astral-sh/uv:0.12.6 AS uv
FROM python:3.12-slim

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
