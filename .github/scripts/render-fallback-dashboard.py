#!/usr/bin/env python3
"""Render a minimal fallback page for the validation dashboard.

Used by the publish-dashboard job in validation-pilot.yml when the combined
run-result artifact could not be downloaded (for example, because the
discovery or completeness job crashed before uploading it). In that case
render-validation-dashboard.py has nothing to render from, but the Pages
deployment must still run -- otherwise whatever was deployed by a previous,
unrelated run would keep looking like the current status. This page makes
the failure visible instead of silently leaving a stale dashboard live.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def render(run_url: str | None) -> str:
    link = (
        f'<a href="{esc(run_url)}">workflow run</a>'
        if run_url
        else "workflow run"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>foundry-samples validation dashboard</title>
<style>
  body {{ background: #ffffff; color: #1b1f23; margin: 0; padding: 2rem; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
  .banner {{ padding: 0.75rem 1rem; border-radius: 6px; margin: 1rem 0; background: #ffebe9; border: 1px solid #cf222e; color: #82071e; }}
  a {{ color: #0969da; }}
</style>
</head>
<body>
<h1>foundry-samples validation dashboard</h1>
<div class="banner">
  &#9888;&#65039; The most recent run's results could not be retrieved or parsed
  (the combined result artifact was missing, failed to download, or contained
  malformed validation data), so this page could not be regenerated. Open the
  {link} for what happened.
</div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-url")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(args.run_url), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
