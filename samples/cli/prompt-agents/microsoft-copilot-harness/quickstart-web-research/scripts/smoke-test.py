from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

AGENT_SERVICE = "web-research-agent"
PYTHON_DOWNLOADS_URL = "https://www.python.org/downloads/"
PROMPT = """What is the latest stable Python release? Use official Python sources.
Return these labeled fields: VERSION, RELEASE_DATE, CHANGE_1, CHANGE_2, RELEASE_URL, and
WHATS_NEW_URL. Cite the official Python release page and What's New page."""


class PythonReleaseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_release_number = False
        self.in_release_link = False
        self.in_release_date = False
        self.pending_version: str | None = None
        self.releases: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "span" and "release-number" in classes:
            self.in_release_number = True
        elif tag == "a" and self.in_release_number:
            href = attributes.get("href") or ""
            self.pending_version = None
            self.in_release_link = href.startswith("/downloads/release/python-")
        elif tag == "span" and "release-date" in classes and self.pending_version:
            self.in_release_date = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self.in_release_link = False
        elif tag == "span":
            self.in_release_number = False
            self.in_release_date = False

    def handle_data(self, data: str) -> None:
        if self.in_release_link:
            match = re.fullmatch(r"\s*Python ([0-9]+\.[0-9]+\.[0-9]+)\s*", data)
            if match:
                self.pending_version = match.group(1)
        elif self.in_release_date and self.pending_version:
            value = data.strip()
            if value:
                self.releases.append((self.pending_version, value))
                self.pending_version = None


def run_azd(*args: str) -> str:
    result = subprocess.run(
        ["azd", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"azd {' '.join(args)} failed with exit code {result.returncode}"
        )
    return result.stdout


def parse_json_output(output: str) -> dict[str, Any]:
    start = output.find("{")
    if start < 0:
        raise AssertionError("azd did not return a JSON object")
    return json.loads(output[start:])


def assert_deployed_definition(payload: dict[str, Any]) -> None:
    latest = payload.get("versions", {}).get("latest", {})
    definition = latest.get("definition", {})
    status = str(latest.get("status") or payload.get("state") or "").lower()
    if status not in {"active", "deployed", "enabled"}:
        raise AssertionError(f"Agent is not active: {status or 'status missing'}")

    if definition.get("kind") != "prompt":
        raise AssertionError("Deployed Agent kind is not prompt")
    if definition.get("harness", {}).get("type") != "microsoft_copilot_preview":
        raise AssertionError("Microsoft Copilot harness is not persisted")

    tools = definition.get("tools", [])
    if not any(tool.get("type") == "web_search" for tool in tools):
        raise AssertionError("Declared Web Search tool is not persisted")

    skills = definition.get("skills", [])
    skill = next(
        (
            item
            for item in skills
            if isinstance(item, dict) and item.get("name") == "official-source-research"
        ),
        None,
    )
    if not skill or not str(skill.get("version", "")).strip():
        raise AssertionError(
            "Immutable official-source-research Skill version is not persisted"
        )


def current_python_release() -> tuple[str, date]:
    request = Request(
        PYTHON_DOWNLOADS_URL,
        headers={
            "Accept-Encoding": "gzip",
            "User-Agent": "quickstart-web-research-smoke-test",
        },
    )
    with urlopen(request, timeout=30) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip" or body.startswith(
            b"\x1f\x8b"
        ):
            body = gzip.decompress(body)
        html = body.decode("utf-8")

    parser = PythonReleaseParser()
    parser.feed(html)
    if not parser.releases:
        raise AssertionError(
            "Could not read the current stable release from Python.org"
        )
    version, release_date = max(
        parser.releases,
        key=lambda release: tuple(int(part) for part in release[0].split(".")),
    )
    return version, parse_release_date(release_date)


def parse_release_date(value: str) -> date:
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", value)
    if iso_match:
        return date(*(int(part) for part in iso_match.groups()))

    month_match = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
        r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?.*?"
        r"\b(\d{1,2}),\s*(\d{4})\b",
        value,
        flags=re.IGNORECASE,
    )
    if not month_match:
        raise AssertionError(f"Could not parse release date: {value}")
    month_number = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }[month_match.group(1)[:3].lower()]
    return date(int(month_match.group(3)), month_number, int(month_match.group(2)))


def labeled_fields(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name in (
        "VERSION",
        "RELEASE_DATE",
        "CHANGE_1",
        "CHANGE_2",
        "RELEASE_URL",
        "WHATS_NEW_URL",
    ):
        match = re.search(
            rf"(?im)^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?"
            rf"(?:\*\*)?{name}(?:\*\*)?[ \t]*:[ \t]*"
            rf"(?=[^ \t\r\n])([^\r\n]+?)[ \t]*$",
            output,
        )
        if not match:
            raise AssertionError(f"Research response is missing labeled field {name}")
        fields[name] = match.group(1).strip()
    return fields


def labeled_url(value: str) -> tuple[str, str]:
    match = re.search(r"https?://[^\s)>\]]+", value)
    if not match:
        raise AssertionError(f"Labeled URL field does not contain a URL: {value}")
    parsed = urlparse(match.group(0))
    return (parsed.hostname or "").lower(), parsed.path.lower()


def assert_research_response(output: str) -> None:
    normalized = output.lower()
    fields = labeled_fields(output)
    version_match = re.search(r"\b(\d+\.\d+\.\d+)\b", fields["VERSION"])
    if not version_match:
        raise AssertionError(
            "Research response does not contain a Python release version"
        )
    reported_version = version_match.group(1)
    reported_date = parse_release_date(fields["RELEASE_DATE"])
    expected_version, expected_date = current_python_release()
    if reported_version != expected_version:
        raise AssertionError(
            f"Agent reported Python {reported_version}; Python.org lists {expected_version}"
        )
    if reported_date != expected_date:
        raise AssertionError(
            f"Agent reported release date {reported_date}; Python.org lists {expected_date}"
        )

    changes = [
        re.sub(r"\s+", " ", fields[name]).strip() for name in ("CHANGE_1", "CHANGE_2")
    ]
    if any(
        len(change) < 12 or change.lower() in {"unknown", "n/a", "none"}
        for change in changes
    ):
        raise AssertionError(
            "Research response contains an empty or inadequate change summary"
        )
    if changes[0].casefold() == changes[1].casefold():
        raise AssertionError("Research response contains duplicate change summaries")

    release_host, release_path = labeled_url(fields["RELEASE_URL"])
    whats_new_host, whats_new_path = labeled_url(fields["WHATS_NEW_URL"])
    version_slug = reported_version.replace(".", "")
    major_minor = ".".join(reported_version.split(".")[:2])
    if release_host not in {"python.org", "www.python.org"}:
        raise AssertionError("Release URL host is not Python.org")
    if not release_path.startswith(f"/downloads/release/python-{version_slug}"):
        raise AssertionError(
            "Research response does not cite an official Python release page"
        )
    if whats_new_host != "docs.python.org" or "/whatsnew/" not in whats_new_path:
        raise AssertionError(
            "Research response does not cite an official What's New page"
        )
    if major_minor not in whats_new_path:
        raise AssertionError(
            "What's New URL does not match the reported Python release"
        )
    if "python.org" not in normalized or "docs.python.org" not in normalized:
        raise AssertionError(
            "Research response does not contain both official Python domains"
        )


def main() -> int:
    print("Checking deployed Agent definition...")
    show = run_azd(
        "ai",
        "agent",
        "show",
        AGENT_SERVICE,
        "--output",
        "json",
        "--no-prompt",
    )
    assert_deployed_definition(parse_json_output(show))

    print("Running the quickstart research scenario...")
    response = run_azd(
        "ai",
        "agent",
        "invoke",
        AGENT_SERVICE,
        PROMPT,
        "--new-conversation",
        "--timeout",
        "600",
        "--no-prompt",
        "--output",
        "raw",
    )
    print(response)
    assert_research_response(response)
    print("PASS: deployed definition and current-source research scenario are valid.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
