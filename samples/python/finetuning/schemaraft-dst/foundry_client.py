"""Keyless Microsoft Foundry client.

Auth is `DefaultAzureCredential` only - there is no API-key path in this sample.
Locally that resolves to your `az login` session; on Azure it resolves to the
managed identity. Either way no secret is ever written to disk.

The bearer token is cached until shortly before expiry. Without that, the OpenAI
SDK calls the token provider on every request, which under
DefaultAzureCredential spawns an `az account get-access-token` subprocess each
time - slow enough to dominate a long evaluation run.
"""
from __future__ import annotations

import os
import time

from azure.identity import DefaultAzureCredential
from openai import OpenAI

SCOPE = "https://ai.azure.com/.default"


class _CachedBearerTokenProvider:
    def __init__(self, scope: str = SCOPE, refresh_margin_seconds: int = 300):
        self._scope = scope
        self._margin = refresh_margin_seconds
        self._credential = DefaultAzureCredential(process_timeout=60)
        self._token: str | None = None
        self._expires_on = 0.0

    def __call__(self) -> str:
        if self._token and time.time() <= self._expires_on - self._margin:
            return self._token
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                tok = self._credential.get_token(self._scope)
                self._token = tok.token
                self._expires_on = float(tok.expires_on)
                return self._token
            except Exception as exc:  # transient DNS / CLI subprocess blips
                last_exc = exc
                time.sleep(2**attempt)
        if self._token:
            return self._token
        raise RuntimeError(
            "could not acquire an Azure token; run `az login`"
        ) from last_exc


def resolve_endpoint(endpoint: str | None = None) -> str:
    """Return the OpenAI-v1 base URL for the Foundry resource."""
    ep = endpoint or os.environ.get("AOAI_ENDPOINT")
    if not ep:
        raise RuntimeError(
            "set AOAI_ENDPOINT (e.g. https://<your-resource>.openai.azure.com) "
            "in your environment or .env"
        )
    ep = ep.rstrip("/")
    if not ep.startswith("https://"):
        raise RuntimeError(f"AOAI_ENDPOINT must be an https URL, got {ep!r}")
    return ep if ep.endswith("/openai/v1") else f"{ep}/openai/v1"


def make_client(endpoint: str | None = None) -> OpenAI:
    return OpenAI(
        base_url=resolve_endpoint(endpoint) + "/",
        api_key=_CachedBearerTokenProvider(),
    )
