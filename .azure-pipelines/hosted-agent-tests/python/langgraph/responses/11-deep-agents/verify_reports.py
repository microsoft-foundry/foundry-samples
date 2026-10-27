"""Verify real named Blob downloads, original preservation, and scoped cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

SOURCE_URL = "https://docs.langchain.com/oss/python/langgraph/overview"
MAX_REPORT_BYTES = 2 * 1024 * 1024


class VerificationError(ValueError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def publication_location(publication: dict, account: str, container: str) -> str:
    parsed = urlsplit(publication.get("download_url", ""))
    filename = publication.get("file_path", "").removeprefix("/")
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != "https"
        or parsed.netloc != f"{account}.blob.core.windows.net"
        or parsed.fragment
        or filename not in {"report-v1.md", "report-v2.md"}
        or re.fullmatch(
            rf"/{re.escape(container)}/[0-9a-f]{{32}}/{re.escape(filename)}",
            parsed.path,
        )
        is None
        or query.get("sp") != ["r"]
        or query.get("spr") != ["https"]
        or not query.get("sig")
        or re.fullmatch(r"[0-9a-f]{64}", publication.get("sha256", "")) is None
    ):
        raise VerificationError("unsafe_publication")
    return parsed.path.removeprefix(f"/{container}/")


def download_report(publication: dict) -> bytes:
    with build_opener(NoRedirects()).open(
        publication["download_url"], timeout=20
    ) as response:
        disposition = Message()
        disposition["content-disposition"] = response.headers.get(
            "Content-Disposition", ""
        )
        if disposition.get_filename() != publication["file_path"].removeprefix("/"):
            raise VerificationError("attachment_name_mismatch")
        content = response.read(MAX_REPORT_BYTES + 1)
    if len(content) > MAX_REPORT_BYTES:
        raise VerificationError("report_too_large")
    if hashlib.sha256(content).hexdigest() != publication["sha256"]:
        raise VerificationError("report_digest_mismatch")
    return content


def delete_blob(account: str, container: str, name: str) -> None:
    executable = shutil.which("az")
    if executable is None:
        raise VerificationError("azure_cli_missing")
    subprocess.run(
        [
            executable,
            "storage",
            "blob",
            "delete",
            "--account-name",
            account,
            "--container-name",
            container,
            "--name",
            name,
            "--auth-mode",
            "login",
            "--only-show-errors",
            "--output",
            "none",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )


def cleanup_roles() -> None:
    if os.environ.get("TF_BUILD", "").lower() != "true":
        return
    hook = Path("hooks/configure-report-storage.py")
    if (
        not hook.is_file()
        or not Path(".azure/report-storage-role-assignments.json").is_file()
    ):
        raise VerificationError("rbac_receipt_missing")
    subprocess.run(
        [sys.executable, str(hook), "--cleanup"],
        check=True,
        capture_output=True,
        timeout=60,
    )


def collect_publications(response: dict) -> list[dict]:
    calls = {}
    for item in response.get("output", []):
        if item.get("type") == "function_call" and item.get("name") == "publish_report":
            arguments = json.loads(item["arguments"])
            calls[item["call_id"]] = arguments.get("report_name")
    publications = []
    for item in response.get("output", []):
        if (
            item.get("type") != "function_call_output"
            or item.get("call_id") not in calls
        ):
            continue
        try:
            publication = json.loads(item["output"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(publication, dict) and publication.get("file_path") == "/" + str(
            calls[item["call_id"]]
        ):
            publications.append(publication)
    return publications


def verify_reports(
    evidence: Path,
    turns: list[int],
    downloader=download_report,
    remover=delete_blob,
    role_remover=cleanup_roles,
) -> None:
    account = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
    container = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "")
    if (
        re.fullmatch(r"[a-z0-9]{3,24}", account) is None
        or re.fullmatch(r"[a-z0-9-]{3,63}", container) is None
    ):
        raise VerificationError("storage_configuration_missing")
    owned = {}
    responses = []
    selected = []
    try:
        for turn in turns:
            path = evidence / f"turn-{turn}-raw.txt"
            if not path.is_file():
                continue
            response = json.loads(path.read_text(encoding="utf-8"))
            responses.append(response)
            publications = collect_publications(response)
            for publication in publications:
                name = publication_location(publication, account, container)
                owned[name] = publication
            selected.append(publications[-1] if publications else None)
        if (
            len(turns) != 3
            or len(responses) != 3
            or any(response.get("status") != "completed" for response in responses)
        ):
            raise VerificationError("incomplete_turns")
        expected = ["/report-v1.md", "/report-v2.md", "/report-v1.md"]
        if any(
            publication is None or publication["file_path"] != filename
            for publication, filename in zip(selected, expected)
        ):
            raise VerificationError("publication_missing")
        if (
            len(
                {
                    publication_location(publication, account, container)
                    for publication in selected
                }
            )
            != 3
        ):
            raise VerificationError("publication_reused_blob")
        original, revised, restored = [
            downloader(publication) for publication in selected
        ]
        if original != restored:
            raise VerificationError("original_report_changed")
        if original != downloader(selected[0]):
            raise VerificationError("original_snapshot_changed")
        if original == revised or b"Recovery Limitations" not in revised:
            raise VerificationError("revision_missing")
        if any(
            SOURCE_URL.encode() not in content
            for content in [original, revised, restored]
        ):
            raise VerificationError("source_citation_missing")
        if any(
            b"Download:" in content or b"sig=" in content
            for content in [original, revised, restored]
        ):
            raise VerificationError("publication_url_saved_in_report")
    finally:
        cleanup_failed = False
        for name in owned:
            try:
                remover(account, container, name)
            except (OSError, VerificationError, subprocess.SubprocessError):
                cleanup_failed = True
        try:
            role_remover()
        except (OSError, VerificationError, subprocess.SubprocessError):
            cleanup_failed = True
        if cleanup_failed:
            raise VerificationError("cleanup_failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--turns", nargs="+", type=int, required=True)
    args = parser.parse_args()
    fingerprint = hashlib.sha256(Path(__file__).read_bytes())
    for key in ["AZURE_STORAGE_ACCOUNT_NAME", "AZURE_STORAGE_CONTAINER_NAME"]:
        fingerprint.update(os.environ.get(key, "").encode())
    for turn in args.turns:
        path = args.evidence_dir / f"turn-{turn}-raw.txt"
        fingerprint.update(str(turn).encode())
        fingerprint.update(path.read_bytes() if path.is_file() else b"missing")
    cache = (
        args.evidence_dir / f"report-verification-{args.turns[0]}-{args.turns[-1]}.json"
    )
    digest = fingerprint.hexdigest()
    if cache.is_file():
        try:
            previous = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        if previous.get("fingerprint") == digest:
            print(json.dumps(previous))
            return 0 if previous["status"] == "passed" else 1
    summary = {"status": "passed", "reason": "reports_verified", "fingerprint": digest}
    try:
        verify_reports(args.evidence_dir, args.turns)
    except VerificationError as error:
        summary.update(status="failed", reason=str(error))
    except (OSError, ValueError, subprocess.SubprocessError):
        summary.update(status="failed", reason="verification_error")
    cache.write_text(json.dumps(summary), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
