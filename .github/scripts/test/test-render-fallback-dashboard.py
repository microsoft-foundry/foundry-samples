#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "render-fallback-dashboard.py"


class RenderFallbackDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, run_url: str | None) -> str:
        output = self.root / "index.html"
        args = [sys.executable, str(SCRIPT), "--output", str(output)]
        if run_url:
            args.extend(["--run-url", run_url])
        completed = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return output.read_text(encoding="utf-8")

    def test_renders_a_page_with_a_link_to_the_run(self) -> None:
        body = self.run_script("https://github.com/o/r/actions/runs/123")
        self.assertIn("<html", body)
        self.assertIn('href="https://github.com/o/r/actions/runs/123"', body)
        self.assertIn("could not be retrieved", body)
        self.assertIn("could not be retrieved or parsed", body)
        self.assertIn("malformed validation data", body)

    def test_renders_a_page_even_without_a_run_url(self) -> None:
        body = self.run_script(None)
        self.assertIn("<html", body)
        self.assertNotIn("href=", body)

    def test_escapes_the_run_url(self) -> None:
        body = self.run_script('https://example.com/"><script>alert(1)</script>')
        self.assertNotIn("<script>alert(1)</script>", body)


if __name__ == "__main__":
    unittest.main()
