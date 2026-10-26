"""Offline tests of response-correlated App Insights ingestion verification."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_trace_evidence as evidence

PROJECT = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account/projects/project"
APPI = "/subscriptions/other/resourceGroups/byo/providers/Microsoft.Insights/components/actual"
LINK = {"application_insights_resource_id": APPI}
START = "2026-10-26T18:00:00Z"


def table(*ids):
    return {"tables": [{"columns": [{"name": "response_id"}, {"name": "name"}],
                        "rows": [[identifier, "invoke_agent"] for identifier in ids]}]}


class EvidenceTests(unittest.TestCase):
    def cli(self, *responses):
        cli = mock.Mock()
        cli.rest.return_value = {"properties": {"AppId": "app-id"}}
        cli.run.side_effect = responses
        return cli

    @mock.patch.object(evidence, "connection", return_value=LINK)
    def test_both_responses_must_be_observed_in_actual_connected_resource(self, _connection):
        cli = self.cli(table("resp_first", "resp_second"))
        result = evidence.verify(cli, PROJECT, ["resp_first", "resp_second"], START)
        self.assertEqual("verified", result["status"])
        self.assertEqual(APPI, cli.rest.call_args.args[1])
        self.assertEqual(APPI, result["application_insights_resource_id"])
        query = evidence.trace_query(["resp_first", "resp_second"], START)
        self.assertTrue(cli.run.call_args.args[-1].startswith("@"))
        self.assertIn('"resp_first"', query)
        self.assertIn('"resp_second"', query)
        self.assertNotIn("customDimensions,", query)

    @mock.patch.object(evidence, "connection", return_value=LINK)
    def test_one_response_is_not_a_pass(self, _connection):
        result = evidence.verify(self.cli(table("resp_first")), PROJECT, ["resp_first", "resp_second"], START, timeout=0)
        self.assertEqual("missing_traces", result["status"])
        self.assertEqual(["resp_second"], result["missing_response_ids"])

    @mock.patch.object(evidence, "connection", return_value=LINK)
    def test_stale_or_unrelated_ids_do_not_pass(self, _connection):
        result = evidence.verify(self.cli(table("resp_unrelated")), PROJECT, ["resp_expected"], START, timeout=0)
        self.assertEqual("missing_traces", result["status"])

    @mock.patch.object(evidence, "connection", return_value=LINK)
    @mock.patch.object(evidence.time, "sleep")
    def test_ingestion_delay_retries_queries_not_agent_invocations(self, sleep, _connection):
        cli = self.cli(table(), table("resp_expected"))
        result = evidence.verify(cli, PROJECT, ["resp_expected"], START)
        self.assertEqual("verified", result["status"])
        self.assertEqual(2, cli.run.call_count)
        sleep.assert_called_once()

    @mock.patch.object(evidence, "connection", return_value=LINK)
    @mock.patch.object(evidence.time, "sleep")
    @mock.patch.object(evidence.time, "monotonic", side_effect=[0, 0, 1])
    def test_empty_ingestion_deadline_is_missing_traces_not_query_error(self, _clock, _sleep, _connection):
        cli = self.cli(table())
        result = evidence.verify(cli, PROJECT, ["resp_expected"], START, timeout=1)
        self.assertEqual("missing_traces", result["status"])
        cli.run.assert_called_once()

    @mock.patch.object(evidence, "connection", return_value=None)
    def test_missing_connection_is_not_a_pass(self, _connection):
        with self.assertRaisesRegex(evidence.AzureError, "no App Insights"):
            evidence.verify(mock.Mock(), PROJECT, ["resp_expected"], START)

    @mock.patch.object(evidence, "connection", return_value=LINK)
    def test_query_permission_error_is_not_empty_success(self, _connection):
        cli = self.cli()
        cli.run.side_effect = evidence.AzureError("AuthorizationFailed")
        with self.assertRaisesRegex(evidence.AzureError, "AuthorizationFailed"):
            evidence.verify(cli, PROJECT, ["resp_expected"], START)

    def test_partial_or_malformed_query_results_are_rejected(self):
        for payload in (
            {"error": {"code": "PartialError"}, **table("resp_expected")},
            {}, {"tables": []},
            {"tables": [{"columns": [{"name": "id"}], "rows": [[]]}]},
        ):
            with self.subTest(payload=payload), self.assertRaises(evidence.AzureError):
                evidence.table_rows(payload)

    def test_query_rejects_missing_timezone_and_invalid_ids(self):
        with self.assertRaises(evidence.AzureError):
            evidence.trace_query(["resp_expected"], "2026-10-26")
        with self.assertRaises(evidence.AzureError):
            evidence.verify(mock.Mock(), PROJECT, ['x"); injected'], START)

    def test_id_markers_are_anchored_and_preserve_distinct_turns(self):
        text = "answer mentions Agent response ID: not-evidence\nAgent response ID: resp_1\r\nAgent response ID: resp_2\n"
        self.assertEqual(["resp_1", "resp_2"], evidence.RESPONSE_PATTERN.findall(text))

    def test_cli_requires_two_distinct_successful_markers_before_querying(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "sample.log"
            log.write_text("Agent response ID: resp_1\nAgent response ID: resp_1\n", encoding="utf-8")
            with mock.patch.object(sys, "argv", [
                "verify", "--project-id", PROJECT, "--sample-log", str(log), "--started-at", START,
            ]), mock.patch.object(evidence, "verify") as verify:
                self.assertEqual(1, evidence.main())
                verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
