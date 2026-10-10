"""Durable snapshot store for the GitHub Copilot session workspace.

The Copilot CLI persists each session — conversation history, planning state,
and per-turn checkpoints — to a local ``config_dir`` (a SQLite ``session-store.db``
plus a ``session-state/<id>/`` tree). ``resume_session`` reads that directory.
On a hosted container **replacement** the local disk is gone, so ``resume_session``
alone is not durable: the conversation would be lost.

This store makes the Copilot session **container-durable** by snapshotting the
per-session ``config_dir`` into the **Foundry StateStore**
(:class:`FoundryStateStore`) at each turn boundary, and restoring it on crash
recovery *before* ``resume_session`` runs — the same durable, platform-managed
store the resilient task itself uses. When no ``FOUNDRY_PROJECT_ENDPOINT`` is
configured (the offline demo), it falls back to an atomic local-file copy so the
sample still runs with no credentials.

Mirrors the two-tier pattern from ``resilient-research``: durable application
state lives in an explicit ``FoundryStateStore`` — small markers hold only a
tiny *reference* (a "snapshot exists" flag); the heavy bytes live here.

The snapshot is a gzip'd tar of the per-session ``config_dir`` tree, base64'd
into a StateStore JSON item. It is taken only **after the Copilot client has
been stopped** for the turn, so the SQLite WAL is checkpointed and the on-disk
DB is consistent. Stale ``*.lock`` files (left by the now-dead process) are
excluded so a restored workspace opens cleanly.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# One store per agent for its Copilot session snapshots. Item keys are the
# session ids; items expire after an hour so abandoned snapshots don't
# accumulate.
_STORE_NAME = "copilot-session-snapshots"
_ITEM_TTL_SECONDS = 3600


def _is_lockfile(name: str) -> bool:
    """Stale per-process lock files must not travel into a restored workspace."""
    base = os.path.basename(name)
    return base.endswith(".lock") or ".lock" in base


def _pack_dir(src: Path) -> bytes:
    """Return a gzip'd tar of *src*'s contents (excluding stale lock files)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for item in sorted(src.rglob("*")):
            if item.is_file() and not _is_lockfile(item.name):
                tar.add(item, arcname=str(item.relative_to(src)))
    return buf.getvalue()


def _unpack_dir(blob: bytes, dst: Path) -> None:
    """Restore a gzip'd tar *blob* into *dst* (created fresh)."""
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        tar.extractall(dst)  # noqa: S202 - trusted, self-produced archive


class SessionSnapshotStore:
    """Durable session-id -> workspace-snapshot store (StateStore, file fallback)."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._base.mkdir(parents=True, exist_ok=True)
        # Use the Foundry StateStore when an endpoint is available; otherwise
        # fall back to the local file store for the offline demo.
        self._use_state_store = bool(os.environ.get("FOUNDRY_PROJECT_ENDPOINT"))
        self._store: Any = None

    async def _state_store(self) -> Any:
        """Lazily resolve (or create) the Foundry StateStore for this agent."""
        if self._store is None:
            from azure.ai.agentserver.core.storage import (  # noqa: PLC0415
                FoundryStateStore,
            )

            self._store = await FoundryStateStore.get_or_create(
                _STORE_NAME,
                item_ttl_seconds=_ITEM_TTL_SECONDS,
            )
        return self._store

    async def save(self, session_id: str, config_dir: Path) -> None:
        """Snapshot the per-session *config_dir* tree under *session_id*.

        Call only after the Copilot client has been stopped so the SQLite WAL
        is checkpointed and the snapshot is consistent.
        """
        if not config_dir.exists():
            return
        blob = _pack_dir(config_dir)
        if self._use_state_store:
            store = await self._state_store()
            # StateStore item values are JSON objects, so base64 the archive.
            await store.set_item(
                session_id, {"tar_gz_b64": base64.b64encode(blob).decode("ascii")}
            )
            logger.info(
                "Saved Copilot session snapshot to StateStore (%d bytes) for %s",
                len(blob),
                session_id,
            )
            return

        target = self._path(session_id)
        fd, tmp = tempfile.mkstemp(
            dir=str(self._base), prefix=f"{session_id}_", suffix=".tgz"
        )
        try:
            with open(fd, "wb") as fh:
                fh.write(blob)
            Path(tmp).replace(target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    async def restore(self, session_id: str, config_dir: Path) -> bool:
        """Restore the snapshot for *session_id* into *config_dir*.

        Returns True if a snapshot was found and restored, else False (a fresh
        session should be created).
        """
        blob: bytes | None = None
        if self._use_state_store:
            store = await self._state_store()
            item = await store.get_item(session_id)
            if item is not None:
                encoded = (item.value or {}).get("tar_gz_b64")
                if encoded:
                    blob = base64.b64decode(encoded)
        else:
            path = self._path(session_id)
            if path.exists():
                blob = path.read_bytes()

        if blob is None:
            return False
        _unpack_dir(blob, config_dir)
        logger.info(
            "Restored Copilot session snapshot (%d bytes) for %s", len(blob), session_id
        )
        return True

    async def delete(self, session_id: str) -> None:
        """Remove the snapshot for *session_id* if present; no-op otherwise."""
        if self._use_state_store:
            from azure.ai.agentserver.core.storage import (  # noqa: PLC0415
                FoundryStorageNotFoundError,
            )

            store = await self._state_store()
            try:
                await store.delete_item(session_id)
            except FoundryStorageNotFoundError:
                pass
            return

        path = self._path(session_id)
        if path.exists():
            path.unlink()

    def _path(self, session_id: str) -> Path:
        return self._base / f"{session_id}.tgz"
