import json
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "agent"))

from main import downstream_context, record

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_real_user import compare


class RoutingTests(unittest.TestCase):
    def real_user_receipts(self):
        evidence = Path(__file__).resolve().parents[1] / "evidence"
        return [
            json.loads((evidence / f"real-user-u{number}.json").read_text(encoding="utf-8"))
            for number in (1, 2)
        ]

    def test_recorded_real_users_are_distinct_and_separate(self):
        result = compare(*self.real_user_receipts())
        self.assertTrue(result["passed"], result)
        self.assertEqual(len(result["checks"]), 6)

    def test_comparison_rejects_shared_session_or_user_or_cross_history(self):
        left, original = self.real_user_receipts()
        for field in ("hosted_session_id", "user_fingerprint"):
            right = copy.deepcopy(original)
            right["receipt"]["downstream"]["receipt"][field] = left["receipt"]["downstream"]["receipt"][field]
            self.assertFalse(compare(left, right)["passed"])
        right = copy.deepcopy(original)
        right["receipt"]["downstream"]["receipt"]["prior_session_messages"].append(
            {"marker": left["receipt"]["downstream"]["receipt"]["marker"]}
        )
        self.assertFalse(compare(left, right)["passed"])

    def test_recorded_same_user_run_has_57_passing_checks(self):
        path = Path(__file__).resolve().parents[1] / "evidence" / "same-user.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["observations"]), 18)
        self.assertEqual(len(result["checks"]), 57)
        self.assertTrue(all(item["passed"] for item in result["checks"]))

    def test_default_does_not_forward_upstream_context(self):
        self.assertIsNone(downstream_context({"marker": "test"}, "upstream"))

    def test_explicit_and_inherited_context(self):
        self.assertEqual(downstream_context({"mode": "inherit"}, "upstream"), "upstream")
        self.assertEqual(
            downstream_context({"mode": "explicit", "c_context_id": "shared"}, "upstream"),
            "shared",
        )

    def test_invalid_mode_and_context_are_rejected(self):
        for payload in [{"mode": "wrong"}, {"mode": "explicit"}, {"mode": "explicit", "c_context_id": ""}]:
            with self.assertRaises(ValueError):
                downstream_context(payload, "upstream")

    def test_ledger_distinguishes_session_from_context_history(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "calls.sqlite"
            first = record(database, "one", {"marker": "A", "caller_agent": "A"})
            other = record(database, "two", {"marker": "B", "caller_agent": "B"})
            repeat = record(database, "one", {"marker": "again", "caller_agent": "B"})
            self.assertEqual(first["prior_session_messages"], [])
            self.assertEqual(len(other["prior_session_messages"]), 1)
            self.assertEqual(other["prior_context_messages"], [])
            self.assertEqual(repeat["prior_context_messages"][0]["marker"], "A")
            json.dumps(repeat)
