# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Token caching utilities for Agent 365 Observability exporter authentication.

Python port of ``token_cache.py`` from the Agent365 reference sample.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


_agentic_token_cache: dict[str, str] = {}


def cache_agentic_token(tenant_id: str, agent_id: str, token: str) -> None:
    """Cache the agentic token for use by Agent 365 Observability exporter."""

    key = f"{tenant_id}:{agent_id}"
    _agentic_token_cache[key] = token
    logger.debug("Cached agentic token for %s", key)


def get_cached_agentic_token(tenant_id: str, agent_id: str) -> str | None:
    """Retrieve a cached agentic token for the Agent 365 Observability exporter."""

    key = f"{tenant_id}:{agent_id}"
    token = _agentic_token_cache.get(key)
    if token:
        logger.debug("Retrieved cached agentic token for %s", key)
    else:
        logger.debug("No cached token found for %s", key)
    return token
