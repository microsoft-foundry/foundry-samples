"""Authenticated recording downloads shared by the voice-agent readback samples."""

import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from azure.core.credentials import TokenCredential
from azure.storage.blob import BlobClient


def validate_blob_uri(blob_uri: str) -> None:
    """Accept an HTTPS Azure Blob URI without embedded credentials or a SAS."""
    try:
        uri = urlsplit(blob_uri)
        hostname = uri.hostname or ""
        valid_host = re.fullmatch(
            r"[a-z0-9]{3,24}\.blob\.core\."
            r"(?:windows\.net|usgovcloudapi\.net|chinacloudapi\.cn)",
            hostname,
        )
        container, separator, blob = uri.path.lstrip("/").partition("/")
        valid_path = (
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])", container)
            and "--" not in container
            and separator
            and unquote(blob).strip("/")
        )
        valid = (
            uri.scheme == "https"
            and valid_host
            and valid_path
            and uri.username is None
            and uri.password is None
            and uri.port is None
            and not uri.query
            and not uri.fragment
            and "?" not in blob_uri
            and "#" not in blob_uri
            and not any(character.isspace() for character in blob_uri)
            and "\\" not in blob_uri
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "BYOS requires an HTTPS Azure Blob URI containing a container and blob, "
            "without a SAS, query, fragment, port, or embedded credentials."
        )


def audio_output_path(
    output_dir: str | Path, conversation_id: str, item_id: str | None = None
) -> Path:
    """Build a local filename without treating service IDs as filesystem paths."""
    identifiers = [conversation_id] + ([item_id] if item_id is not None else [])
    for identifier in identifiers:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier) or len(identifier) > 160:
            raise ValueError(
                "Conversation and item IDs must be safe filename components."
            )
    return Path(output_dir) / ("_".join(identifiers) + ".wav")


def write_audio_file(chunks: Iterable[bytes], output_path: str | Path) -> Path:
    """Publish a complete nonempty download without overwriting an existing file."""
    output = Path(output_path)
    if output.exists() or output.is_symlink():
        raise FileExistsError(
            f"Refusing to overwrite an existing output file: {output}"
        )
    if not output.parent.is_dir():
        raise ValueError("The audio output directory must already exist.")
    staging = output.with_name(f".{output.name}.{uuid4().hex}.partial")
    staging_created = False
    try:
        size = 0
        with staging.open("xb") as stream:
            staging_created = True
            for chunk in chunks:
                stream.write(chunk)
                size += len(chunk)
            if not size:
                raise RuntimeError("The audio download was empty; no file was saved.")
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link publishes the completed file atomically and fails if another writer
        # created the destination after the initial check. Unlike replace(), it cannot clobber.
        os.link(staging, output)
    finally:
        if staging_created:
            staging.unlink(missing_ok=True)
    return output


def save_recording(
    output_path: str | Path,
    *,
    credential: TokenCredential | None,
    blob_uri: str | None,
    download: Callable[[], Iterable[bytes]],
) -> Path:
    """Use the metadata-selected storage route; never fall back after a BYOS failure.

    The caller owns the credential lifetime. BYOS requires that identity to have
    Storage Blob Data Reader (or equivalent) on the customer's recording container.
    No connection strings, account keys, or SAS tokens are accepted or printed.
    """
    output = Path(output_path)
    if output.exists() or output.is_symlink():
        raise FileExistsError(
            f"Refusing to overwrite an existing output file: {output}"
        )
    if not output.parent.is_dir():
        raise ValueError("The audio output directory must already exist.")
    if blob_uri is not None:
        validate_blob_uri(blob_uri)
        if credential is None:
            raise ValueError("BYOS downloads require the caller's Azure credential.")
        with BlobClient.from_blob_url(
            blob_uri, credential=credential, logging_enable=False
        ) as blob:
            return write_audio_file(
                blob.download_blob(logging_enable=False).chunks(), output
            )
    return write_audio_file(download(), output)
