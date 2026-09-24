# Copyright (c) Microsoft. All rights reserved.

"""Shared Redis client used by every custom store in this sample.

All four custom stores (responses, agent sessions, workflow checkpoints, and
function approvals) persist to a single Redis instance. One shared async client
is opened lazily and reused. Every store namespaces its keys by a common prefix
and a per-user partition, so one caller cannot read another caller's state. A
shared write lock serializes the few read-modify-write flows so concurrent
requests cannot interleave.
"""

from __future__ import annotations

import asyncio
import hashlib
import os

import redis.asyncio as redis
from redis_entraid.cred_provider import create_from_default_azure_credential

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_LOCAL_USER_ID = "local-developer"
DEFAULT_REDIS_PORT = 10000
KEY_PREFIX = "custom-store"
# Microsoft Entra ID scope for the Azure Cache for Redis / Azure Managed Redis
# data plane. DefaultAzureCredential exchanges the agent's managed identity for
# a token in this scope.
REDIS_ENTRA_SCOPE = "https://redis.azure.com/.default"


def partition_for(user_id: str | None, local_user_id: str) -> str:
    """Return a non-identifying tenant partition for the resolved user.

    Hashing keeps caller identifiers out of stored keys while still isolating
    every user's data. Local development requests fall back to ``local_user_id``.
    """
    resolved = user_id if user_id else local_user_id
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()


class RedisDatabase:
    """Own the shared async Redis client and build namespaced keys.

    When ``host`` is set the client connects to Azure Managed Redis over TLS and
    authenticates passwordless with the agent's managed identity through
    ``DefaultAzureCredential``. Otherwise it connects to the local Redis at
    ``url`` without authentication for development.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        host: str | None = None,
        port: int = DEFAULT_REDIS_PORT,
    ) -> None:
        self._url = url
        self._host = host
        self._port = port
        self._client: redis.Redis | None = None
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    @property
    def write_lock(self) -> asyncio.Lock:
        """Serialize read-modify-write flows across concurrent requests."""
        return self._write_lock

    def key(self, *parts: str) -> str:
        """Build a namespaced key from the shared prefix and the given parts."""
        return ":".join((KEY_PREFIX, *parts))

    def partition_key(self, namespace: str, partition: str, *parts: str) -> str:
        """Build a partitioned key that is safe for Redis Cluster transactions.

        Redis Cluster hashes only the value inside braces when a key contains a
        hash tag. Using the per-user partition as that tag keeps every key that
        can participate in one transaction or multi-key command in the same
        slot while preserving isolation between users.
        """
        return self.key(namespace, f"{{{partition}}}", *parts)

    async def connect(self) -> redis.Redis:
        """Open the shared client on first use and reuse it thereafter."""
        if self._client is not None:
            return self._client
        async with self._init_lock:
            if self._client is None:
                # decode_responses keeps every stored value as ``str`` so the
                # stores can serialize and deserialize JSON without byte handling.
                if self._host:
                    # Passwordless: the credential provider refreshes the Entra
                    # ID token in the background and supplies it to every
                    # (re)connection.
                    credential_provider = create_from_default_azure_credential(
                        (REDIS_ENTRA_SCOPE,)
                    )
                    self._client = redis.Redis(
                        host=self._host,
                        port=self._port,
                        ssl=True,
                        decode_responses=True,
                        credential_provider=credential_provider,
                    )
                else:
                    self._client = redis.from_url(self._url, decode_responses=True)
        return self._client


def create_database() -> RedisDatabase:
    """Create the shared database from Redis configuration.

    An explicitly configured ``REDIS_URL`` selects local Redis. Otherwise,
    ``REDIS_HOST`` selects passwordless Azure Managed Redis (injected by the azd
    ``redis`` layer). With neither setting, the local Redis default is used.
    """
    url = os.getenv("REDIS_URL", "").strip()
    if url:
        return RedisDatabase(url=url)
    host = os.getenv("REDIS_HOST", "").strip()
    if host:
        port = int(os.getenv("REDIS_PORT", str(DEFAULT_REDIS_PORT)).strip() or DEFAULT_REDIS_PORT)
        return RedisDatabase(host=host, port=port)
    return RedisDatabase(url=DEFAULT_REDIS_URL)


def get_local_user_id() -> str:
    """Read the developer identity used to partition local, unhosted requests."""
    return os.getenv("LOCAL_STORE_USER_ID", DEFAULT_LOCAL_USER_ID).strip() or DEFAULT_LOCAL_USER_ID
