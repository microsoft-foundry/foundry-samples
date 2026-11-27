"""Download a published report using the caller's Microsoft Entra identity."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobClient


def download_report(blob_url: str, sha256: str, destination: Path) -> Path:
    """Read an Entra-protected Blob and save it only after digest verification."""
    parsed = urlsplit(blob_url)
    if (
        parsed.scheme != "https"
        or re.fullmatch(
            r"[a-z0-9]{3,24}\.blob\.core\.(windows\.net|usgovcloudapi\.net|chinacloudapi\.cn)",
            parsed.hostname or "",
        )
        is None
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(parsed.path.strip("/").split("/")) < 2
    ):
        raise ValueError(
            "Use an Azure Blob HTTPS URL without a SAS token or query string."
        )
    if re.fullmatch(r"[0-9a-fA-F]{64}", sha256) is None:
        raise ValueError("Use the SHA256 digest returned by publish_report.")
    with (
        DefaultAzureCredential() as credential,
        BlobClient.from_blob_url(blob_url, credential=credential) as blob,
    ):
        content = blob.download_blob().readall()
    if hashlib.sha256(content).hexdigest() != sha256.lower():
        raise ValueError("Downloaded report does not match the publication SHA256.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blob-url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    destination = download_report(
        arguments.blob_url, arguments.sha256, arguments.output
    )
    print(f"Downloaded and verified {destination}")


if __name__ == "__main__":
    main()
