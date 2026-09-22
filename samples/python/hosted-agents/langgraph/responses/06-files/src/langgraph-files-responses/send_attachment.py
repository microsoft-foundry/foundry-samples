# Copyright (c) Microsoft. All rights reserved.

"""Send an image or PDF directly to the locally running Responses agent."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from openai import OpenAI

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
}


def main() -> None:
    """Encode a local attachment and print the agent's response.

    The file is sent to the local host, which forwards it to the configured
    model service. No session upload or filesystem tool is involved.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="PNG, JPEG, WebP, GIF, or PDF file")
    parser.add_argument("--prompt", default="Describe the attached image or document.")
    parser.add_argument("--port", type=int, default=8088, help="Local agent port")
    args = parser.parse_args()
    media_type = MEDIA_TYPES.get(args.file.suffix.lower())
    if media_type is None:
        parser.error("Choose a PNG, JPEG, WebP, GIF, or PDF file.")
    try:
        data = args.file.read_bytes()
    except OSError as exc:
        parser.error(str(exc))
    if not data:
        parser.error("The attachment must not be empty.")
    uri = f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
    attachment = (
        {"type": "input_file", "filename": args.file.name, "file_data": uri}
        if media_type == "application/pdf"
        else {"type": "input_image", "image_url": uri, "detail": "auto"}
    )
    with OpenAI(base_url=f"http://localhost:{args.port}", api_key="local") as client:
        response = client.responses.create(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": args.prompt},
                        attachment,
                    ],
                }
            ],
            store=False,
        )
    if response.status != "completed":
        raise SystemExit(f"Agent response {response.status}: {response.error}")
    print(response.output_text)


if __name__ == "__main__":
    main()
