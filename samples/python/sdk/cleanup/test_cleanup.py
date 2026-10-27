import contextlib
import io
import sys
import unittest
from unittest.mock import patch
import cleanup


class CleanupGuardTests(unittest.TestCase):
    def test_confirmation_is_required_before_any_resource_operation(self):
        with (
            patch.object(sys, "argv", ["cleanup.py", "agent", "test-agent"]),
            patch.object(cleanup, "delete_resource") as delete,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as result:
                cleanup.main()
            self.assertNotEqual(result.exception.code, 0)
            delete.assert_not_called()

    def test_confirmed_identifier_is_passed_without_substitution(self):
        with (
            patch.object(
                sys, "argv", ["cleanup.py", "agent", "test-agent", "--confirm"]
            ),
            patch.object(cleanup, "delete_resource") as delete,
        ):
            cleanup.main()
            self.assertEqual(delete.call_args.args[0:2], ("agent", "test-agent"))


if __name__ == "__main__":
    unittest.main()
