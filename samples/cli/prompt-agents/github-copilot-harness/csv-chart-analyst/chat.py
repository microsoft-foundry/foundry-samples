from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from azure.identity import AzureCliCredential

AGENT_NAME = "csv-chart-analyst"
MODEL_NAME = "gpt-5.4-mini"


def validated_project_endpoint(project_endpoint: str) -> str:
    parsed = urlsplit(project_endpoint.strip())
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path.rstrip("/")
    path_parts = path.split("/")
    if parsed.scheme.lower() != "https":
        raise ValueError("Foundry project endpoint must use HTTPS")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError(
            "Foundry project endpoint must not include credentials or a custom port"
        )
    if not hostname.endswith(".services.ai.azure.com"):
        raise ValueError(
            "Foundry project endpoint host must end with .services.ai.azure.com"
        )
    if parsed.query or parsed.fragment:
        raise ValueError(
            "Foundry project endpoint must not include a query string or fragment"
        )
    if (
        len(path_parts) != 4
        or path_parts[1:3] != ["api", "projects"]
        or path_parts[3] in {"", ".", ".."}
    ):
        raise ValueError(
            "Foundry project endpoint path must be /api/projects/<project>"
        )
    return urlunsplit(("https", parsed.netloc, path, "", ""))


class FoundryClient:
    def __init__(self, project_endpoint: str) -> None:
        self.project_endpoint = validated_project_endpoint(project_endpoint)
        self.agent_name = AGENT_NAME
        self.agent_endpoint = f"{self.project_endpoint}/agents/{quote(self.agent_name)}/endpoint/protocols/openai"
        self.credential = AzureCliCredential()

    @property
    def feature_headers(self) -> dict[str, str]:
        return {"Foundry-Features": "GitHubCopilot=V1Preview"}

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        token = self.credential.get_token("https://ai.azure.com/.default").token
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        timeout = kwargs.pop("timeout", 60)
        response = requests.request(
            method, url, headers=headers, timeout=timeout, **kwargs
        )
        if not response.ok:
            try:
                detail = json.dumps(response.json(), indent=2)
            except ValueError:
                detail = response.text
            raise RuntimeError(
                f"Foundry request failed ({response.status_code}):\n{detail}"
            )
        return response

    def upload_csv(self, csv_path: Path) -> str:
        with csv_path.open("rb") as csv_file:
            response = self.request(
                "POST",
                f"{self.project_endpoint}/openai/v1/files",
                data={"purpose": "assistants"},
                files={"file": (csv_path.name, csv_file, "text/csv")},
            )
        return response.json()["id"]

    def create_conversation(self) -> str:
        response = self.request(
            "POST",
            f"{self.agent_endpoint}/conversations?api-version=v1",
            headers={"Content-Type": "application/json", **self.feature_headers},
            json={},
        )
        return response.json()["id"]

    def respond(
        self, conversation_id: str, prompt: str, file_id: str
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": MODEL_NAME,
            "conversation": {"id": conversation_id},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_file", "file_id": file_id},
                    ],
                }
            ],
            "background": True,
        }

        response = self.request(
            "POST",
            f"{self.agent_endpoint}/responses?api-version=v1",
            headers={"Content-Type": "application/json", **self.feature_headers},
            json=body,
        )
        result = response.json()
        response_id = result["id"]
        deadline = time.monotonic() + 900

        while result.get("status") in {"queued", "in_progress"}:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Response {response_id} is still {result.get('status')} after 15 minutes"
                )
            time.sleep(3)
            result = self.request(
                "GET",
                f"{self.agent_endpoint}/responses/{quote(response_id)}?api-version=v1",
                headers=self.feature_headers,
            ).json()

        return result

    def download_generated_file(self, file_id: str, output_path: Path) -> None:
        response = self.request(
            "GET",
            f"{self.project_endpoint}/openai/v1/files/{quote(file_id)}/content",
        )
        output_path.write_bytes(response.content)


def azd_env_value(name: str) -> str:
    configured = os.environ.get(name)
    if configured:
        return configured

    result = subprocess.run(
        ["azd", "env", "get-value", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def response_text_and_files(
    response: dict[str, Any],
    excluded_file_ids: set[str] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    text_parts: list[str] = []
    files_by_id: dict[str, dict[str, str]] = {}
    excluded_file_ids = excluded_file_ids or set()
    has_file_label = False
    file_label = r"(?:File:|\*\*File:\*\*|\*\*File\*\*:)"
    download_id_label = r"(?:Download ID:|\*\*Download ID:\*\*|\*\*Download ID\*\*:)"

    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") != "output_text":
                continue
            content_text = content.get("text", "")
            if content_text:
                text_parts.append(content_text)
                if re.search(
                    r"(?im)^[ \t]*(?:\*\*)?File(?:\*\*)?:",
                    content_text,
                ):
                    has_file_label = True
                for file_match in re.finditer(
                    rf"(?im)^[ \t]*{file_label}[ \t]*"
                    r"`?([^`\r\n]+?)`?[ \t]*(?:\r?\n[ \t]*)+"
                    rf"{download_id_label}[ \t]*"
                    r"`?([A-Za-z][A-Za-z0-9_-]+)`?[ \t]*$",
                    content_text,
                ):
                    filename = file_match.group(1).strip()
                    file_id = file_match.group(2)
                    if file_id not in excluded_file_ids:
                        files_by_id.setdefault(
                            file_id,
                            {"file_id": file_id, "filename": filename},
                        )
            for annotation in content.get("annotations", []):
                if annotation.get("type") == "file_citation":
                    file_id = annotation.get("file_id")
                    filename = annotation.get("filename")
                    if file_id and filename and file_id not in excluded_file_ids:
                        files_by_id[file_id] = {
                            "file_id": file_id,
                            "filename": filename,
                        }

    text = "\n".join(text_parts)
    if not has_file_label:
        filename_matches = re.findall(
            r"\b([A-Za-z0-9][A-Za-z0-9._-]*\.(?:csv|json|jpe?g|pdf|png|svg|txt|webp|xlsx))\b",
            text,
            flags=re.IGNORECASE,
        )
        file_id_match = re.search(
            rf"(?im)^[ \t]*{download_id_label}[ \t]*" r"`?([A-Za-z][A-Za-z0-9_-]+)`?",
            text,
        )
        if filename_matches and file_id_match:
            filename = filename_matches[-1]
            file_id = file_id_match.group(1)
            if file_id not in excluded_file_ids:
                files_by_id.setdefault(
                    file_id,
                    {"file_id": file_id, "filename": filename},
                )

    return text, list(files_by_id.values())


def run_prompt(
    client: FoundryClient,
    conversation_id: str,
    file_id: str,
    prompt: str,
    output_dir: Path,
) -> None:
    response = client.respond(conversation_id, prompt, file_id)
    if response.get("status") != "completed":
        raise RuntimeError(json.dumps(response.get("error") or response, indent=2))

    text, generated_files = response_text_and_files(
        response,
        excluded_file_ids={file_id},
    )
    print(f"\nAgent: {text or '[No text response]'}")

    for generated_file in generated_files:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / Path(generated_file["filename"]).name
        client.download_generated_file(generated_file["file_id"], output_path)
        print(f"Downloaded: {output_path.resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attach a CSV to the GitHub Copilot harness analyst and download generated Foundry Files."
        )
    )
    parser.add_argument("csv", type=Path, help="CSV file to analyze")
    parser.add_argument(
        "--prompt",
        action="append",
        default=[],
        help="Prompt to run non-interactively; repeat for a multi-turn test",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for generated files (default: outputs)",
    )
    parser.add_argument(
        "--project-endpoint",
        default=None,
        help="Foundry project endpoint; defaults to FOUNDRY_PROJECT_ENDPOINT from the azd environment",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = args.csv.resolve()
    if not csv_path.is_file() or csv_path.suffix.lower() != ".csv":
        print(f"CSV file not found or not a .csv file: {csv_path}", file=sys.stderr)
        return 2

    project_endpoint = args.project_endpoint or azd_env_value(
        "FOUNDRY_PROJECT_ENDPOINT"
    )
    client = FoundryClient(project_endpoint)

    print(f"Uploading {csv_path.name}...")
    file_id = client.upload_csv(csv_path)
    print(f"Uploaded file: {file_id}")

    conversation_id = client.create_conversation()
    print(f"Conversation: {conversation_id}")

    if args.prompt:
        for prompt in args.prompt:
            print(f"\nYou: {prompt}")
            run_prompt(client, conversation_id, file_id, prompt, args.output_dir)
        return 0

    print("Ask about the CSV or request a chart. Enter 'quit' to stop.")
    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if prompt.lower() in {"quit", "exit"}:
            break
        if prompt:
            run_prompt(client, conversation_id, file_id, prompt, args.output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
