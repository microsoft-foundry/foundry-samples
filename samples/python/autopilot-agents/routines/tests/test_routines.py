"""Synthetic lifecycle tests; no Azure credentials or channel transport."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from azure.ai.projects.aio.operations import BetaRoutinesOperations
from azure.ai.projects.models import Routine, TimerRoutineTrigger
from azure.core.exceptions import ResourceNotFoundError, ServiceResponseError
from microsoft_agents.activity import Activity
from openai import OpenAIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import app, routines

UTC = timezone.utc
AT = datetime(2099, 1, 15, 12, 10, 0, 123456, UTC)
LOG = logging.getLogger("routines.offline")


def wire(value):
    encoder = BetaRoutinesOperations.create_or_update.__wrapped__.__globals__["SdkJSONEncoder"]
    return json.loads(json.dumps(value, cls=encoder, exclude_readonly=True))


class Context:
    def __init__(self, text="", chat="chat", *, send_error=None):
        self.activity = Activity.model_validate({
            "type": "message", "text": text, "timestamp": AT.isoformat(), "localTimezone": "UTC",
            "channelId": "msteams", "serviceUrl": "https://example.invalid",
            "from": {"id": "sender", "aadObjectId": "sender-aad"},
            "recipient": {
                "id": "bot", "role": "agenticUser", "agenticAppId": "app",
                "agenticUserId": "instance", "tenantId": "tenant",
            },
            "conversation": {"id": chat, "conversationType": "personal", "tenantId": "tenant"},
        })
        self.sent = []
        self.send_error = send_error

    async def send_activity(self, activity):
        if self.send_error:
            raise self.send_error
        self.sent.append(activity)


def scope(context=None):
    return routines.build_routine_scope(
        context or Context(), agent_name="sample", blueprint_id="blueprint", expected_tenant_id="tenant",
    )


class MemoryRoutines:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.faults = {}

    def fault(self, operation):
        queue = self.faults.get(operation, [])
        return queue.pop(0) if queue else None

    async def list(self):
        self.calls.append(("list",))
        for value in deepcopy(list(self.records.values())):
            yield Routine(wire(value))

    async def get(self, name):
        self.calls.append(("get", name))
        mode = self.fault("get")
        if mode == "error":
            raise ServiceResponseError("Synthetic readback unavailable")
        if mode == "missing" or name not in self.records:
            raise ResourceNotFoundError("Synthetic absence")
        value = deepcopy(self.records[name])
        if mode == "conflict":
            value["action"]["tenant_id"] = "foreign"
        return Routine(wire(value))

    async def create_or_update(self, name, body, **kwargs):
        assert kwargs == {"retry_total": 0}
        self.calls.append(("create", name))
        mode = self.fault("create")
        if mode != "not_committed":
            self.records[name] = deepcopy({"name": name, **body})
        if mode:
            raise ServiceResponseError("Synthetic response unavailable")

    async def enable(self, name, **kwargs):
        await self.change_enabled("enable", name, True, kwargs)

    async def disable(self, name, **kwargs):
        await self.change_enabled("disable", name, False, kwargs)

    async def change_enabled(self, operation, name, enabled, kwargs):
        assert kwargs == {"retry_total": 0}
        self.calls.append((operation, name))
        mode = self.fault(operation)
        if mode != "not_committed":
            self.records[name]["enabled"] = enabled
        if mode:
            raise ServiceResponseError("Synthetic response unavailable")

    @property
    def operations(self):
        return [call[0] for call in self.calls]

    @property
    def mutations(self):
        return [name for name in self.operations if name in {"create", "enable", "disable"}]


class RoutineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scope = scope()
        self.sdk = MemoryRoutines()
        self.guards = [patch(target, side_effect=AssertionError("Network forbidden")) for target in (
            "socket.getaddrinfo", "socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection",
        )]
        self.guards.append(patch.dict(os.environ, {
            "FOUNDRY_AGENT_NAME": "sample", "FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID": "blueprint",
            "FOUNDRY_AGENT_TENANT_ID": "tenant", "AZURE_AI_MODEL_DEPLOYMENT_NAME": "offline-fixture",
        }))
        for guard in self.guards:
            guard.start()
        app._scope_locks.clear()

    async def asyncTearDown(self):
        app._scope_locks.clear()
        for guard in reversed(self.guards):
            guard.stop()

    def timer(self):
        return routines.build_timer_routine_spec(self.scope, at=AT, message_text="Keep <literal>\nUTC")

    def schedule(self, message="Hydrate", zone="UTC"):
        return routines.build_scheduled_routine_spec(
            self.scope, cron_expression="*/10 * * * *", time_zone=zone, message_text=message,
        )

    def seed(self, spec, *, enabled=True):
        record = wire({"name": spec.name, **spec.body})
        record["enabled"] = enabled
        self.sdk.records[spec.name] = record
        return deepcopy(record)

    async def start(self, spec):
        return await routines.ensure_only_started(self.sdk, spec, scope=self.scope, logger=LOG)

    async def test_native_timer_wire_and_unknown_UTC_metadata_are_preserved(self):
        spec = self.timer()
        record = wire({"name": spec.name, **spec.body})
        trigger = record["triggers"]["delivery"]
        self.assertEqual(datetime.fromisoformat(trigger["at"].replace("Z", "+00:00")), AT.replace(microsecond=0))
        self.assertEqual(trigger["time_zone"], "UTC")
        dto = Routine(record)
        self.assertIsInstance(dto.triggers["delivery"], TimerRoutineTrigger)
        self.assertEqual(dto.as_dict()["triggers"]["delivery"], trigger)
        self.assertTrue(routines.routine_matches(dto, spec))

    async def test_timer_ISO_and_unix_readbacks_keep_identity_and_whole_seconds(self):
        spec = self.timer()
        for numeric in (False, True):
            with self.subTest(numeric=numeric):
                record = self.seed(spec)
                if numeric:
                    record["triggers"]["delivery"]["at"] = int(AT.timestamp())
                before = deepcopy(record)
                dto = Routine(record)
                self.assertTrue(routines.routine_matches(dto, spec))
                found = routines._scheduled_spec_from_routine(dto, self.scope)
                self.assertIsNotNone(found)
                self.assertEqual((found.name, found.owner, found.body), (spec.name, spec.owner, spec.body))
                self.assertEqual(found.schedule.at, AT.replace(microsecond=0))
                self.assertEqual(record, before)

    async def test_timer_create_discover_reuse_disable_and_reenable(self):
        spec = self.timer()
        self.assertEqual(await self.start(spec), routines.StartOutcome.CREATED)
        self.assertEqual(self.sdk.operations, ["list", "get", "create", "get"])
        original = deepcopy(self.sdk.records)
        self.sdk.calls.clear()
        self.assertEqual(await self.start(spec), routines.StartOutcome.ALREADY_ENABLED)
        self.assertEqual(self.sdk.operations, ["list", "get"])
        self.assertEqual(self.sdk.records, original)
        state = await routines.list_owned_routines(self.sdk, self.scope, logger=LOG)
        self.assertEqual([item.name for item in state.active], [spec.name])
        self.sdk.calls.clear()
        self.assertEqual(await routines.ensure_scope_stopped(self.sdk, self.scope, logger=LOG),
                         routines.StopOutcome.STOPPED)
        self.assertEqual(self.sdk.operations, ["list", "get", "disable", "get"])
        self.sdk.calls.clear()
        self.assertEqual(await self.start(spec), routines.StartOutcome.REENABLED)
        self.assertEqual(self.sdk.operations, ["list", "get", "enable", "get"])
        self.assertEqual(self.sdk.records, original)

    async def test_missing_or_changed_timer_metadata_remains_a_conflict(self):
        spec = self.timer()
        for changes in (None, {"time_zone": None}, {"time_zone": "Etc/UTC"}, {"time_zone": "Europe/London"},
                        {"unknown": "extra"}, {"at": "not-a-time"}):
            with self.subTest(changes=changes):
                record = self.seed(spec)
                if changes is None:
                    del record["triggers"]["delivery"]["time_zone"]
                else:
                    record["triggers"]["delivery"].update(changes)
                self.sdk.records[spec.name] = record
                before = deepcopy(self.sdk.records)
                self.sdk.calls.clear()
                self.assertFalse(routines.routine_matches(Routine(record), spec))
                self.assertEqual(await self.start(spec), routines.StartOutcome.CONFLICT)
                self.assertEqual(self.sdk.operations, ["list"])
                self.assertEqual(self.sdk.records, before)

    async def test_foreign_malformed_and_multiple_owned_records_do_not_mutate(self):
        spec = self.schedule()
        for case in ("foreign_owner", "destination", "payload", "malformed", "multiple"):
            with self.subTest(case=case):
                self.sdk = MemoryRoutines()
                record = self.seed(spec)
                if case == "foreign_owner":
                    record["description"] = "foreign"
                elif case == "destination":
                    record["action"]["tenant_id"] = "foreign"
                elif case == "payload":
                    record["action"]["input"]["value"]["text"] = "changed"
                elif case == "malformed":
                    del record["action"]["input"]["recipient"]["agenticUserId"]
                else:
                    self.seed(self.schedule("Other"))
                self.sdk.records[spec.name] = record
                before = deepcopy(self.sdk.records)
                self.assertEqual(await self.start(spec), routines.StartOutcome.CONFLICT)
                self.assertEqual(await routines.ensure_scope_stopped(self.sdk, self.scope, logger=LOG),
                                 routines.StopOutcome.AMBIGUOUS if case == "multiple" else routines.StopOutcome.CONFLICT)
                self.assertEqual(self.sdk.mutations, [])
                self.assertEqual(self.sdk.records, before)

    async def test_disabled_alias_reuses_exact_raw_id_and_body(self):
        for stored, requested in (("Etc/UTC", "UTC"), ("UTC", "Etc/UTC")):
            with self.subTest(stored=stored, requested=requested):
                self.sdk = MemoryRoutines()
                raw = routines._build_routine_spec(
                    self.scope, schedule=routines.RoutineSchedule("*/10 * * * *", stored), message_text="Hydrate",
                )
                record = self.seed(raw, enabled=False)
                self.assertEqual(await self.start(self.schedule(zone=requested)), routines.StartOutcome.REENABLED)
                record["enabled"] = True
                self.assertEqual(self.sdk.records, {raw.name: record})
                self.assertEqual(self.sdk.calls, [("list",), ("get", raw.name), ("enable", raw.name), ("get", raw.name)])

    async def test_timeout_reconciliation_outcomes_and_single_mutation(self):
        expected_success = {
            "create": routines.StartOutcome.CREATED_AFTER_RECONCILIATION,
            "enable": routines.StartOutcome.REENABLED,
            "disable": routines.StopOutcome.STOPPED_AFTER_RECONCILIATION,
        }
        for operation in ("create", "enable", "disable"):
            for readback in ("matching", "missing", "conflict", "error"):
                with self.subTest(operation=operation, readback=readback):
                    self.sdk = MemoryRoutines()
                    spec = self.schedule()
                    if operation != "create":
                        self.seed(spec, enabled=operation == "disable")
                    self.sdk.faults[operation] = ["committed"]
                    if readback != "matching":
                        self.sdk.faults["get"] = [None, readback]
                    if operation == "disable":
                        outcome = await routines.ensure_scope_stopped(self.sdk, self.scope, logger=LOG)
                        expected = (expected_success[operation] if readback in {"matching", "missing"} else
                                    routines.StopOutcome.CONFLICT if readback == "conflict" else routines.StopOutcome.UNCERTAIN)
                    else:
                        outcome = await self.start(spec)
                        expected = (expected_success[operation] if readback == "matching" else
                                    routines.StartOutcome.CONFLICT if readback == "conflict" else routines.StartOutcome.UNCERTAIN)
                    self.assertEqual(outcome, expected)
                    self.assertEqual(self.sdk.operations, ["list", "get", operation, "get"])
                    self.assertEqual(self.sdk.mutations, [operation])

    async def test_timeout_without_commit_never_reports_success(self):
        for operation in ("create", "enable", "disable"):
            with self.subTest(operation=operation):
                self.sdk = MemoryRoutines()
                spec = self.schedule()
                if operation != "create":
                    self.seed(spec, enabled=operation == "disable")
                before = deepcopy(self.sdk.records)
                self.sdk.faults[operation] = ["not_committed"]
                outcome = (await routines.ensure_scope_stopped(self.sdk, self.scope, logger=LOG)
                           if operation == "disable" else await self.start(spec))
                self.assertEqual(outcome.value, "uncertain")
                self.assertEqual(self.sdk.records, before)
                self.assertEqual(self.sdk.mutations, [operation])
                self.assertEqual(self.sdk.operations, ["list", "get", operation, "get"])

    async def test_same_chat_waits_for_model_while_another_chat_progresses(self):
        entered, release = asyncio.Event(), asyncio.Event()
        model_calls = []

        async def parse(**kwargs):
            text = json.loads(kwargs["input"])["user_text"]
            model_calls.append(text)
            if text == "first":
                entered.set()
                await release.wait()
                result = app.Schedule(kind="schedule", cron="*/10 * * * *", time_zone="UTC",
                                      message="Hydrate", summary="every ten minutes")
            elif text == "second":
                result = app.Stop(kind="stop")
            else:
                result = app.Else(kind="else", answer="Other chat")
            return SimpleNamespace(output_parsed=app.ModelResult(result=result))

        project = self.project(parse)
        first = asyncio.create_task(app.handle_model_message(Context("first"), project))
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(app.handle_model_message(Context("second"), project))
        try:
            await asyncio.wait_for(app.handle_model_message(Context("other", "other-chat"), project), 2)
            self.assertEqual(model_calls, ["first", "other"])
            self.assertEqual(self.sdk.mutations, [])
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(first, second), 2)
        self.assertEqual(model_calls, ["first", "other", "second"])
        self.assertEqual(self.sdk.mutations, ["create", "disable"])
        self.assertFalse(next(iter(self.sdk.records.values()))["enabled"])

    async def test_scope_lock_releases_after_model_error_send_error_or_cancellation(self):
        for failure in ("model", "send", "cancel"):
            with self.subTest(failure=failure):
                entered, release = asyncio.Event(), asyncio.Event()

                async def parse(**kwargs):
                    if json.loads(kwargs["input"])["user_text"] == "first":
                        entered.set()
                        await release.wait()
                        if failure == "model":
                            raise OpenAIError("Synthetic parser error")
                    return SimpleNamespace(output_parsed=app.ModelResult(
                        result=app.Else(kind="else", answer="No change")))

                project = self.project(parse)
                first = asyncio.create_task(app.handle_model_message(
                    Context("first", send_error=RuntimeError("Synthetic send") if failure == "send" else None), project))
                await asyncio.wait_for(entered.wait(), 2)
                second_context = Context("second")
                second = asyncio.create_task(app.handle_model_message(second_context, project))
                try:
                    if failure == "cancel":
                        first.cancel()
                    release.set()
                    if failure in {"send", "cancel"}:
                        with self.assertRaises(RuntimeError if failure == "send" else asyncio.CancelledError):
                            await first
                    else:
                        await first
                    await asyncio.wait_for(second, 2)
                    self.assertEqual(len(second_context.sent), 1)
                    self.assertEqual(self.sdk.mutations, [])
                finally:
                    release.set()
                    await asyncio.gather(first, second, return_exceptions=True)

    def project(self, parse):
        class Model:
            responses = SimpleNamespace(parse=parse)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

        def get_openai_client(**kwargs):
            self.assertEqual(kwargs, {"max_retries": 0})
            return Model()

        return SimpleNamespace(beta=SimpleNamespace(routines=self.sdk), get_openai_client=get_openai_client)


if __name__ == "__main__":
    unittest.main()
