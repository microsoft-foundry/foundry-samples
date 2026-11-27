FROM python:3.12-slim AS runtime
WORKDIR /app

# Copy source. The build context is the agent project root
# (foundry-autopilot-email-assistant/src/foundry_m365_autopilot),
# so we land the package at /app/foundry_m365_autopilot.
COPY . /app/foundry_m365_autopilot/

RUN if [ -f /app/foundry_m365_autopilot/requirements.txt ]; then \
    pip install --no-cache-dir -r /app/foundry_m365_autopilot/requirements.txt; \
    fi

EXPOSE 8088

ENV PORT=8088
ENV HOST=0.0.0.0
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV MCP_PLATFORM_ENDPOINT=https://agent365.svc.cloud.microsoft

# -----------------------------------------------------------------------------
# Microsoft 365 Agents SDK configuration
#
# The Python ``load_configuration_from_env`` helper splits env-var names on
# ``__`` and stores the leaves verbatim. The MSAL connection manager then
# looks up the literal key ``SERVICE_CONNECTION`` (with an underscore) inside
# the ``CONNECTIONS`` dict, so the env-var names MUST be in ALL-CAPS and use
# ``SERVICE_CONNECTION`` (single underscore inside the connection name).
#
# The C#-style mixed-case ``Connections__ServiceConnection__Settings__*`` env
# vars from appsettings.json do NOT work on Linux/Python.
# -----------------------------------------------------------------------------

ENV CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHTYPE=IdentityProxyManager
ENV CONNECTIONS__SERVICE_CONNECTION__SETTINGS__SCOPES__0=5a807f24-c9de-44ee-a3a7-329e88a00ffc/.default

ENV CONNECTIONSMAP__0__SERVICEURL=*
ENV CONNECTIONSMAP__0__CONNECTION=SERVICE_CONNECTION


# -----------------------------------------------------------------------------
# AgentApplication configuration
#
# Mirrors the ``AgentApplication`` section from appsettings.json. Nested keys
# are flattened with ``__`` and stored verbatim by
# ``load_configuration_from_env``. The ``AGENTIC`` handler key matches
# ``AUTH_HANDLER_NAME`` (see below).
# -----------------------------------------------------------------------------
ENV AGENTAPPLICATION__STARTTYPINGTIMER=false
ENV AGENTAPPLICATION__REMOVERECIPIENTMENTION=false
ENV AGENTAPPLICATION__NORMALIZEMENTIONS=false
ENV AGENTAPPLICATION__USERAUTHORIZATION__AUTOSIGNIN=false
ENV AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__TYPE=AgenticUserAuthorization
# Auth-handler scopes must be a space-delimited string (parsed by
# AuthHandler._format_scopes via str.strip().split(" ")). Do NOT use the
# indexed ``SCOPES__0=...`` form here — that yields a dict and crashes
# with ``'dict' object has no attribute 'strip'`` at startup. The indexed
# form only works for the CONNECTIONS section.
ENV AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES=5a807f24-c9de-44ee-a3a7-329e88a00ffc/.default


# -----------------------------------------------------------------------------
# Azure OpenAI Responses API configuration is injected when the hosted agent
# version is created.
# -----------------------------------------------------------------------------

ENTRYPOINT ["python", "-m", "foundry_m365_autopilot"]
