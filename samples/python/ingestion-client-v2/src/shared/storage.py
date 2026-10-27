"""Keyless blob storage helpers for the input (audio) and output (results) accounts."""
import json
import logging
import os
from functools import lru_cache
from tempfile import SpooledTemporaryFile
from typing import List, Optional

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

_credential_singleton: Optional[DefaultAzureCredential] = None


def credential() -> DefaultAzureCredential:
    global _credential_singleton
    if _credential_singleton is None:
        client_id = os.environ.get("AZURE_CLIENT_ID")
        _credential_singleton = DefaultAzureCredential(managed_identity_client_id=client_id)
    return _credential_singleton


def endpoint(account: str) -> str:
    if account == "output":
        return os.environ["OUTPUT_STORAGE_BLOB_ENDPOINT"]
    return os.environ["INPUT_STORAGE_BLOB_ENDPOINT"]


@lru_cache(maxsize=4)
def _service(blob_endpoint: str) -> BlobServiceClient:
    return BlobServiceClient(account_url=blob_endpoint, credential=credential())


def service(account: str) -> BlobServiceClient:
    return _service(endpoint(account))


def account_name(account: str) -> str:
    # https://<name>.blob.core.windows.net/  ->  <name>
    return endpoint(account).split("//", 1)[1].split(".", 1)[0]


def download(container: str, blob: str, account: str = "input") -> bytes:
    client = service(account).get_blob_client(container, blob)
    return client.download_blob().readall()


def download_to_spooled(
    container: str, blob: str, account: str = "input", max_mem: int = 64 * 1024 * 1024
) -> SpooledTemporaryFile:
    """Stream a blob into a spooled temp file (memory up to max_mem, then spills to disk).

    Keeps memory bounded for long/large audio instead of loading it all into RAM.
    """
    client = service(account).get_blob_client(container, blob)
    spooled: SpooledTemporaryFile = SpooledTemporaryFile(max_size=max_mem)
    client.download_blob().readinto(spooled)
    spooled.seek(0)
    return spooled


def get_blob_size(container: str, blob: str, account: str = "input") -> Optional[int]:
    client = service(account).get_blob_client(container, blob)
    try:
        return client.get_blob_properties().size
    except Exception:  # noqa: BLE001 - size is best-effort
        return None


def upload(
    container: str,
    blob: str,
    data: bytes,
    account: str,
    content_type: str = "application/octet-stream",
) -> None:
    client = service(account).get_blob_client(container, blob)
    client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type=content_type))


def write_result(blob_name: str, result: dict) -> None:
    container = os.environ["OUTPUT_CONTAINER"]
    payload = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
    upload(container, f"{blob_name}.json", payload, account="output", content_type="application/json")


def write_error(blob_name: str, message: str) -> None:
    container = os.environ["ERRORS_CONTAINER"]
    payload = json.dumps({"source": blob_name, "error": message}, ensure_ascii=False, indent=2).encode("utf-8")
    upload(container, f"{blob_name}.error.json", payload, account="output", content_type="application/json")


def quarantine(source_container: str, blob: str, reason: str) -> None:
    """Copy an unprocessable source blob into the quarantine container with a reason note."""
    data = download(source_container, blob, account="input")
    qcontainer = os.environ["QUARANTINE_CONTAINER"]
    upload(qcontainer, blob, data, account="input")
    note = json.dumps({"source": blob, "reason": reason}, ensure_ascii=False, indent=2).encode("utf-8")
    upload(qcontainer, f"{blob}.reason.json", note, account="input", content_type="application/json")
    logging.info("Quarantined %s (%s)", blob, reason)


def write_json(container: str, blob: str, obj: dict, account: str) -> None:
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    upload(container, blob, payload, account=account, content_type="application/json")


def list_blobs(container: str, account: str = "output") -> List[str]:
    client = service(account).get_container_client(container)
    return [b.name for b in client.list_blobs()]


def delete_blob(container: str, blob: str, account: str) -> None:
    service(account).get_blob_client(container, blob).delete_blob()
