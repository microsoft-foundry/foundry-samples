# Copyright (c) Microsoft. All rights reserved.

"""Shared utilities — redaction for logging and public tool output."""

import json
import re

_REDACT_PATTERNS = [
    (re.compile(r"(accessKey=)[^&\s\"']+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"\beyJ[a-zA-Z0-9._-]{20,}\b"), "<token>"),
]


def redact(text: str) -> str:
    """Redact tokens and secrets from text for safe logging/display."""
    for pat, rep in _REDACT_PATTERNS:
        text = pat.sub(rep, text)
    return text


def public_tool_output(
    name: str, output: str, live_view_urls: list[str],
) -> str:
    if name == "load_skill":
        return output

    def sanitize_json(value):
        if isinstance(value, dict):
            if value.get("type") == "image":
                return {"type": "text", "text": "Screenshot omitted for privacy."}
            return {
                key: (
                    "Screenshot omitted for privacy."
                    if key.replace("_", "").replace(" ", "").lower() == "screenshot"
                    else sanitize_json(item)
                )
                for key, item in value.items()
                if key.replace("_", "").replace(" ", "").lower() != "liveviewurl"
            }
        if isinstance(value, list):
            return [sanitize_json(item) for item in value]
        return sanitize_text(value) if isinstance(value, str) else value

    def sanitize_text(text: str) -> str:
        prefix = next(
            (item for item in ("Tool error: ", "Tool call failed: ")
             if text.startswith(item)),
            "",
        )
        text = text[len(prefix):]
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, (dict, list)):
            sanitized = sanitize_json(value)
            if sanitized != value:
                return prefix + json.dumps(sanitized, ensure_ascii=False)
        for url in live_view_urls:
            if url:
                text = text.replace(url, "[live-view URL omitted]")
                text = text.replace(
                    json.dumps(url, ensure_ascii=False)[1:-1],
                    "[live-view URL omitted]",
                )
        return prefix + redact(text)

    return sanitize_text(output)
