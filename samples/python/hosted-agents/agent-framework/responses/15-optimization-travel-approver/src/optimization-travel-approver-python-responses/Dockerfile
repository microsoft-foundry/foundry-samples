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

COPY . .

EXPOSE 8088

# vNext (ADC): Append the egress proxy CA cert to system and Python cert bundles
# so that outbound HTTPS (App Insights, Azure services, etc.) works correctly.

CMD ["bash", "-c", "if [ -f /etc/ssl/certs/adc-egress-proxy-ca.crt ]; then cat /etc/ssl/certs/adc-egress-proxy-ca.crt >> /etc/ssl/certs/ca-certificates.crt && cat /etc/ssl/certs/adc-egress-proxy-ca.crt >> $(.venv/bin/python -c 'import certifi; print(certifi.where())'); fi && exec .venv/bin/python main.py"]
