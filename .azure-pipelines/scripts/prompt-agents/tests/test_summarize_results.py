"""Offline checks for fail-closed matrix result summaries."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "summarize_results.py"
SPEC = importlib.util.spec_from_file_location("prompt_summary", SCRIPT)
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


class SummaryTests(unittest.TestCase):
    def test_missing_invalid_and_failed_recovery_are_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entries = [{"comboId": "cli-prompt-agents-basic", "samplePath": "samples/basic",
                        "executionProfile": "prompt"}]
            run = root / "PromptAgentResult-cli-prompt-agents-basic/run"
            run.mkdir(parents=True)
            result = run / "result.json"
            for content, expected in ((None, "missing/invalid result"), ("{}", "missing/invalid result"),
                                      ('{"status":"failed"}', "failed"), ('{"status":"passed"}', "failed recovery")):
                with self.subTest(content=content):
                    if content is not None:
                        result.write_text(content, encoding="utf-8")
                    text, failed = summary.summarize(entries, root)
                    self.assertIn(f"| samples/basic | prompt | {expected} |", text)
                    self.assertEqual(failed, expected != "passed")
            (run / "recovery-result.json").write_text(json.dumps({"status": "cleanup-only", "exit_code": 1}), encoding="utf-8")
            text, failed = summary.summarize(entries, root)
            self.assertTrue(failed)
            self.assertIn("failed recovery", text)
            (run / "recovery-result.json").write_text(json.dumps({"status": "cleanup-only", "exit_code": 0,
                "cleanup_status": "complete"}), encoding="utf-8")
            text, failed = summary.summarize(entries, root)
            self.assertFalse(failed)

    def test_unsafe_combo_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unsafe combo ID"):
                summary.summarize([{"comboId": "../escape"}], Path(directory))


if __name__ == "__main__":
    unittest.main()
