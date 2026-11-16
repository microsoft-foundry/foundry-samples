from __future__ import annotations

import re


def redact_sensitive_values(text: str) -> str:
    text = re.sub(
        r"(Authorization:\s*Bearer\s+)[^\s\"']+",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(--access-token\s+)(\"[^\"]+\"|'[^']+'|\S+)", r"\1<redacted>", text)
    text = re.sub(
        r"(access_token=)[^&\s\"']+", r"\1<redacted>", text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"(accessToken=)[^&\s\"']+", r"\1<redacted>", text, flags=re.IGNORECASE
    )
    text = re.sub(r"(accessKey=)[^&\s\"']+", r"\1<redacted>", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "<redacted-jwt>", text
    )
    return text
