import asyncio
import base64
import copy
import importlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, patch


SRC = Path(__file__).resolve().parents[1] / "src" / "resilient-copilot"
sys.path.insert(0, str(SRC))

import agent
from azure.ai.agentserver.core.storage import FoundryStateStore
from azure.ai.agentserver.core.tasks import TaskContext
from copilot._jsonrpc import JsonRpcClient
from copilot.session import CopilotSession
from copilot.session_events import SessionEventType
from copilot.session_events import SessionEvent
from copilot_session import (
    CopilotHarness,
    CopilotSessionError,
    ElicitationDecisionRequest,
    ElicitationRequest,
    HarnessClosingError,
    IdleBoundary,
    NativeInputRequest,
    TodoCheckpointRequest,
)
import store as snapshot_module
import copilot_session as copilot_session_module
from store import (
    SessionSnapshotStore,
    SnapshotTooLargeError,
    _pack_dir,
    _unpack_dir,
    session_storage_key,
    todo_fingerprint,
    validate_session_id,
)
import main


class SnapshotSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_fingerprint_rejects_core_links_before_any_target_read(self):
        for name in ("session.db", "plan.md"):
            with self.subTest(name=name):
                workspace = self.root / name.replace(".", "-")
                workspace.mkdir()
                linked = workspace / name
                with patch.object(
                    Path,
                    "is_symlink",
                    autospec=True,
                    side_effect=lambda path: path == linked,
                ), patch.object(
                    snapshot_module.sqlite3, "connect"
                ) as connect, patch.object(
                    Path, "read_bytes", autospec=True
                ) as read:
                    with self.assertRaisesRegex(ValueError, "regular file"):
                        todo_fingerprint(workspace)
                connect.assert_not_called()
                read.assert_not_called()

    def test_session_ids_are_validated_and_filesystem_keys_are_hashed(self):
        valid = "A_b-9" * 20
        self.assertEqual(validate_session_id(valid), valid)
        key = session_storage_key(valid)
        self.assertEqual(len(key), 64)
        self.assertNotIn(valid, key)
        for invalid in (
            "",
            "../escape",
            r"..\escape",
            "/absolute",
            r"C:\absolute",
            "has/slash",
            "has\\slash",
            "x" * 121,
            "é",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_session_id(invalid)

    def test_pack_skips_links_before_database_or_jsonl_reads(self):
        source = self.root / "source"
        source.mkdir()
        (source / "keep.txt").write_text("keep", encoding="utf-8")
        link_names = {"linked.db", "linked.jsonl", "linked.txt"}
        for name in link_names:
            (source / name).write_text("outside fixture\n", encoding="utf-8")
        with patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=lambda item: item.name in link_names,
        ), patch.object(snapshot_module, "_sqlite_backup") as backup, patch.object(
            snapshot_module, "_complete_jsonl_prefix_size"
        ) as prefix:
            blob = _pack_dir(source, live=True)
        backup.assert_not_called()
        prefix.assert_not_called()
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            self.assertEqual(archive.getnames(), ["keep.txt"])

    def test_pack_and_restore_exclude_real_outside_and_broken_symlinks(self):
        source = self.root / "source"
        source.mkdir()
        outside = self.root / "outside.txt"
        outside.write_text("outside fixture\n", encoding="utf-8")
        (source / "keep.txt").write_text("keep", encoding="utf-8")
        try:
            for name in ("linked.db", "linked.jsonl", "linked.txt"):
                (source / name).symlink_to(outside)
            (source / "broken.db").symlink_to(self.root / "missing")
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable")
            raise
        for live in (False, True):
            with self.subTest(live=live):
                blob = _pack_dir(source, live=live)
                with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
                    self.assertEqual(archive.getnames(), ["keep.txt"])
                destination = self.root / f"restored-{live}"
                _unpack_dir(blob, destination)
                self.assertEqual((destination / "keep.txt").read_text(), "keep")
                self.assertEqual(
                    list(destination.iterdir()), [destination / "keep.txt"]
                )
        self.assertEqual(outside.read_text(), "outside fixture\n")

    def test_archive_rejects_traversal_before_replacing_destination(self):
        destination = self.root / "destination"
        destination.mkdir()
        (destination / "keep.txt").write_text("keep", encoding="utf-8")
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode="w:gz") as archive:
            info = tarfile.TarInfo("../escape.txt")
            info.size = 3
            archive.addfile(info, io.BytesIO(b"bad"))
        with self.assertRaisesRegex(ValueError, "Unsafe snapshot"):
            _unpack_dir(blob.getvalue(), destination)
        self.assertEqual((destination / "keep.txt").read_text(), "keep")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_archive_restores_legacy_windows_member_names_safely(self):
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode="w:gz") as archive:
            info = tarfile.TarInfo(r"session-state\test\value.txt")
            info.size = 2
            archive.addfile(info, io.BytesIO(b"ok"))
        destination = self.root / "destination"
        _unpack_dir(blob.getvalue(), destination)
        self.assertEqual(
            (destination / "session-state" / "test" / "value.txt").read_text(),
            "ok",
        )

    async def test_local_restore_reads_legacy_filename_into_safe_directory(self):
        source = self.root / "source"
        source.mkdir()
        (source / "session-store.db").write_bytes(b"db")
        snapshots = SessionSnapshotStore(self.root / "snapshots")
        snapshots._use_state_store = False
        snapshots._legacy_path("legacy").write_bytes(_pack_dir(source))
        destination = self.root / session_storage_key("legacy")
        self.assertTrue(await snapshots.restore("legacy", destination))
        self.assertEqual((destination / "session-store.db").read_bytes(), b"db")

    async def test_state_store_allows_two_mib_and_rejects_over_five_mib(self):
        config = self.root / "config"
        config.mkdir()
        snapshots = SessionSnapshotStore(self.root / "snapshots")
        snapshots._use_state_store = True
        cloud = SimpleNamespace(set_item=AsyncMock())
        snapshots._store = cloud
        with patch.object(
            SessionSnapshotStore,
            "_snapshot_selection",
            return_value=([], set(), set(), None, {}),
        ), patch.object(
            snapshot_module, "_pack_selected", return_value=b"x" * (2 * 1024 * 1024)
        ):
            await snapshots.save("test", config)
        cloud.set_item.assert_awaited_once()

        cloud.set_item.reset_mock()
        with patch.object(
            SessionSnapshotStore,
            "_snapshot_selection",
            return_value=([], set(), set(), None, {}),
        ), patch.object(
            snapshot_module, "_pack_selected", return_value=b"x" * (4 * 1024 * 1024)
        ), self.assertRaisesRegex(
            SnapshotTooLargeError, "5 MiB serialized JSON"
        ):
            await snapshots.save("test", config)
        cloud.set_item.assert_not_awaited()

    def test_live_jsonl_prefix_is_streamed_without_read_bytes(self):
        config = self.root / "config"
        config.mkdir()
        complete = b'{"type":"saved"}\n' * 10_000
        (config / "events.jsonl").write_bytes(complete + b'{"partial":')

        with patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("live JSONL must be streamed"),
        ):
            blob = _pack_dir(config, live=True)

        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            restored = archive.extractfile("events.jsonl")
            self.assertIsNotNone(restored)
            self.assertEqual(restored.read(), complete)

    async def test_oversized_pack_preserves_previous_cloud_snapshot(self):
        old_config = self.root / "old-config"
        old_config.mkdir()
        (old_config / "session-store.db").write_bytes(b"old snapshot")
        old_value = {
            "tar_gz_b64": base64.b64encode(_pack_dir(old_config)).decode("ascii")
        }

        config = self.root / "config"
        config.mkdir()
        cloud = SimpleNamespace(
            set_item=AsyncMock(),
            get_item=AsyncMock(return_value=SimpleNamespace(value=old_value)),
        )
        snapshots = SessionSnapshotStore(self.root / "snapshots")
        snapshots._use_state_store = True
        snapshots._store = cloud
        with patch.object(
            SessionSnapshotStore,
            "_snapshot_selection",
            return_value=([], set(), set(), None, {}),
        ), patch.object(
            snapshot_module, "_pack_selected", return_value=b"x" * (4 * 1024 * 1024)
        ), self.assertRaisesRegex(
            SnapshotTooLargeError, "5 MiB serialized JSON"
        ):
            await snapshots.save("test", config)
        cloud.set_item.assert_not_awaited()

        restored = self.root / "restored"
        self.assertTrue(await snapshots.restore("test", restored))
        self.assertEqual((restored / "session-store.db").read_bytes(), b"old snapshot")

    async def test_versioned_store_uses_thirty_days_and_reads_legacy_cloud_item(self):
        snapshots = SessionSnapshotStore(self.root / "snapshots")
        snapshots._use_state_store = True
        created = SimpleNamespace(get_item=AsyncMock(return_value=None))
        legacy_blob = _pack_dir(self.root)
        legacy = SimpleNamespace(
            get_item=AsyncMock(
                return_value=SimpleNamespace(
                    value={"tar_gz_b64": base64.b64encode(legacy_blob).decode("ascii")}
                )
            )
        )
        snapshots._store = created
        snapshots._legacy_store = legacy
        destination = self.root / "restored"
        self.assertTrue(await snapshots.restore("test", destination))
        legacy.get_item.assert_awaited_once_with("test")

        snapshots = SessionSnapshotStore(self.root / "snapshots-2")
        snapshots._use_state_store = True
        resolved = SimpleNamespace()
        with patch.object(
            FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=resolved),
        ) as get_or_create:
            self.assertIs(await snapshots._state_store(), resolved)
        self.assertEqual(
            get_or_create.call_args.kwargs["item_ttl_seconds"],
            30 * 24 * 60 * 60,
        )
        self.assertEqual(
            get_or_create.call_args.args[0], "copilot-session-snapshots-v2"
        )

    async def test_missing_legacy_store_is_absent_with_real_local_backend(self):
        state_root = self.root / "real-core-state"
        destination = self.root / "fresh-config"
        with patch.dict(
            os.environ,
            {
                "AGENTSERVER_STATE_ROOT": str(state_root),
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.test",
                "FOUNDRY_HOSTING_ENVIRONMENT": "",
            },
            clear=False,
        ):
            snapshots = SessionSnapshotStore(self.root / "snapshots-real")
            self.assertTrue(snapshots._use_state_store)
            self.assertFalse(await snapshots.restore("fresh", destination))
            await snapshots.aclose()

        self.assertFalse(destination.exists())
        documents = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in state_root.rglob("*.json")
        ]
        store_names = {document["store"]["name"] for document in documents}
        self.assertIn("copilot-session-snapshots-v2", store_names)
        self.assertNotIn("copilot-session-snapshots", store_names)


class HarnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_bearer_token_provider_refreshes_and_credential_closes(self):
        credential = SimpleNamespace(
            get_token=AsyncMock(
                side_effect=[
                    SimpleNamespace(token="first"),
                    SimpleNamespace(token="second"),
                ]
            ),
            close=AsyncMock(),
        )
        harness = CopilotHarness()
        with patch.dict(
            os.environ,
            {
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.test",
                "AZURE_AI_MODEL_DEPLOYMENT_NAME": "model",
            },
            clear=True,
        ), patch("azure.identity.aio.DefaultAzureCredential", return_value=credential):
            self.assertTrue(harness.has_backend())
            provider, model = harness._byok_provider()
        self.assertEqual(model, "model")
        self.assertEqual(provider["base_url"], "https://example.test")
        callback = provider["bearer_token_provider"]
        self.assertEqual(await callback({}), "first")
        self.assertEqual(await callback({}), "second")
        self.assertEqual(credential.get_token.await_count, 2)
        await harness.close()
        credential.close.assert_awaited_once()

    async def test_model_endpoint_override_preserves_storage_project(self):
        for project in ("https://storage.example.test", ""):
            with self.subTest(project=project):
                credential = SimpleNamespace(close=AsyncMock())
                harness = CopilotHarness()
                with patch.dict(
                    os.environ,
                    {
                        "FOUNDRY_PROJECT_ENDPOINT": project,
                        "AZURE_AI_MODEL_ENDPOINT": "https://model.example.test",
                        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "model",
                    },
                    clear=True,
                ), patch(
                    "azure.identity.aio.DefaultAzureCredential", return_value=credential
                ):
                    self.assertTrue(harness.has_backend())
                    provider, model = harness._byok_provider()
                    self.assertEqual(os.environ["FOUNDRY_PROJECT_ENDPOINT"], project)
                self.assertEqual(provider["base_url"], "https://model.example.test")
                self.assertEqual(provider["wire_api"], "responses")
                self.assertEqual(model, "model")
                await harness.close()
                credential.close.assert_awaited_once()

    def test_model_endpoint_without_deployment_does_not_enable_backend(self):
        harness = CopilotHarness()
        with patch.dict(
            os.environ,
            {"AZURE_AI_MODEL_ENDPOINT": "https://model.example.test"},
            clear=True,
        ), patch("azure.identity.aio.DefaultAzureCredential") as credential:
            self.assertFalse(harness.has_backend())
            self.assertEqual(harness._byok_provider(), (None, None))
            credential.assert_not_called()

    async def test_resume_failure_never_creates_fresh_session(self):
        harness = CopilotHarness()
        client = SimpleNamespace(
            start=AsyncMock(),
            resume_session=AsyncMock(side_effect=OSError("corrupt session")),
            create_session=AsyncMock(),
            stop=AsyncMock(),
        )
        with patch("copilot_session.CopilotClient", return_value=client), patch.dict(
            os.environ, {"GITHUB_TOKEN": "test"}, clear=True
        ), patch.object(harness, "_byok_provider", return_value=(None, None)):
            with self.assertRaisesRegex(OSError, "corrupt session"):
                await harness.start("test", recover=True)
        client.create_session.assert_not_awaited()
        client.stop.assert_awaited_once()

    async def test_session_error_is_forwarded_then_terminates_iterator(self):
        harness = CopilotHarness()
        event = SimpleNamespace(type=SessionEventType.SESSION_ERROR, data="failed")
        harness._on_event(event)
        events = harness.events()
        self.assertIs(await anext(events), event)
        with self.assertRaisesRegex(CopilotSessionError, "failed"):
            await anext(events)

    async def test_close_rejects_pending_control(self):
        harness = CopilotHarness()
        pending = asyncio.create_task(harness.queue_input("input", "prompt", "enqueue"))
        await asyncio.sleep(0)
        await harness.close()
        with self.assertRaises(HarnessClosingError):
            await pending

    async def test_pinned_dispatcher_orders_idle_around_send_response(self):
        async def exercise(order):
            harness = CopilotHarness()
            loop = asyncio.get_running_loop()
            rpc = JsonRpcClient(
                SimpleNamespace(
                    stdin=SimpleNamespace(write=lambda _data: None, flush=lambda: None)
                )
            )
            rpc._loop = loop
            idle = SimpleNamespace(type=SessionEventType.SESSION_IDLE)
            ordinary = SimpleNamespace(type=SessionEventType.ASSISTANT_INTENT)
            rpc.set_notification_handler(
                lambda _method, params: harness._on_event(
                    idle if params["kind"] == "idle" else ordinary
                )
            )
            harness.session = SimpleNamespace(
                _client=rpc,
                session_id="session",
                abort=AsyncMock(),
            )
            sending = asyncio.create_task(
                harness.send("follow up", mode="enqueue", causal_idle=True)
            )
            while not rpc.pending_requests:
                await asyncio.sleep(0)
            request_id = next(iter(rpc.pending_requests))

            messages = {
                "ordinary": {
                    "jsonrpc": "2.0",
                    "method": "session.event",
                    "params": {"kind": "ordinary"},
                },
                "idle": {
                    "jsonrpc": "2.0",
                    "method": "session.event",
                    "params": {"kind": "idle"},
                },
                "response": {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"messageId": "message-id"},
                },
            }
            thread = threading.Thread(
                target=lambda: [rpc._handle_message(messages[name]) for name in order]
            )
            thread.start()
            await asyncio.to_thread(thread.join)
            self.assertEqual(await asyncio.wait_for(sending, 2), "message-id")
            return harness, idle, ordinary

        stale_harness, stale_idle, ordinary = await exercise(
            ("ordinary", "idle", "response")
        )
        self.assertIs(
            await asyncio.wait_for(anext(stale_harness.events()), 2), ordinary
        )
        waiting = asyncio.create_task(anext(stale_harness.events()))
        await asyncio.sleep(0)
        self.assertFalse(waiting.done())
        stale_harness._on_event(stale_idle)
        self.assertIs(await asyncio.wait_for(waiting, 2), stale_idle)

        current_harness, current_idle, _ = await exercise(("response", "idle"))
        self.assertIs(
            await asyncio.wait_for(anext(current_harness.events()), 2),
            current_idle,
        )

    async def test_cancelled_send_barrier_cleans_receiver_without_event_loss(self):
        release = asyncio.Event()

        class Client:
            async def request(self, method, params, *, on_response_inline):
                await release.wait()
                return {"messageId": "never"}

        harness = CopilotHarness()
        harness.session = SimpleNamespace(_client=Client(), session_id="session")
        sending = asyncio.create_task(
            harness.send("follow up", mode="enqueue", causal_idle=True)
        )
        await asyncio.sleep(0)
        sending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await sending

        event = SimpleNamespace(type=SessionEventType.ASSISTANT_INTENT)
        harness._on_event(event)
        self.assertIs(await asyncio.wait_for(anext(harness.events()), 2), event)
        self.assertFalse(
            any(
                "_next_event" in repr(task.get_coro())
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task() and not task.done()
            )
        )

    async def test_cancelled_send_barrier_preserves_concurrently_dequeued_event(self):
        release = asyncio.Event()

        class Client:
            async def request(self, method, params, *, on_response_inline):
                await release.wait()
                return {"messageId": "never"}

        harness = CopilotHarness()
        harness.session = SimpleNamespace(_client=Client(), session_id="session")
        event = SimpleNamespace(type=SessionEventType.ASSISTANT_INTENT)
        harness._enqueue_event(event)
        original_wait = copilot_session_module.asyncio.wait

        async def cancel_after_receiver_finishes(tasks, **kwargs):
            receive = next(
                task for task in tasks if "_next_event" in repr(task.get_coro())
            )
            await original_wait({receive}, return_when=asyncio.ALL_COMPLETED)
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

        with patch.object(
            copilot_session_module.asyncio,
            "wait",
            side_effect=cancel_after_receiver_finishes,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await harness.send("follow up", mode="enqueue", causal_idle=True)

        self.assertIs(await asyncio.wait_for(anext(harness.events()), 2), event)

    async def test_sdk_reader_thread_events_wake_loop_in_debug_mode(self):
        harness = CopilotHarness()
        loop = asyncio.get_running_loop()
        old_debug = loop.get_debug()
        errors = []
        old_handler = loop.get_exception_handler()
        loop.set_debug(True)
        loop.set_exception_handler(lambda _loop, context: errors.append(context))
        events = [
            SimpleNamespace(type=SessionEventType.ASSISTANT_INTENT, value=index)
            for index in range(3)
        ]
        idle = SimpleNamespace(type=SessionEventType.SESSION_IDLE, value=3)
        try:
            thread = threading.Thread(
                target=lambda: [harness._on_event(event) for event in [*events, idle]]
            )
            thread.start()
            await asyncio.to_thread(thread.join)
            received = [event async for event in harness.events()]
            self.assertEqual(received, [*events, idle])
            await harness.close()
            after_close = threading.Thread(target=lambda: harness._on_event(events[0]))
            after_close.start()
            await asyncio.to_thread(after_close.join)
            await asyncio.sleep(0)
        finally:
            loop.set_exception_handler(old_handler)
            loop.set_debug(old_debug)
        self.assertEqual(errors, [])
        self.assertTrue(harness._queue.empty())

    async def test_pinned_elicitation_dispatcher_waits_for_consumer_ack(self):
        response_started = asyncio.Event()
        response_release = asyncio.Event()

        class Client:
            async def request(self, method, params):
                response_started.set()
                await response_release.wait()
                return {"success": True}

        harness = CopilotHarness()
        sdk_session = CopilotSession("session", Client())
        sdk_session._elicitation_handler = harness._elicitation_handler
        event = SessionEvent.from_dict(
            {
                "type": "elicitation.requested",
                "id": "00000000-0000-0000-0000-000000000001",
                "timestamp": "2026-10-12T00:00:00Z",
                "data": {
                    "requestId": "request-1",
                    "message": "Continue?",
                },
            }
        )
        sdk_session._dispatch_event(event)

        request = await asyncio.wait_for(harness._queue.get(), 2)
        self.assertIsInstance(request, ElicitationRequest)
        self.assertFalse(response_started.is_set())
        request.acknowledged.set_result(None)
        self.assertTrue(
            harness.answer_elicitation(request.elicitation_id, "accept", {})
        )
        await asyncio.wait_for(response_started.wait(), 2)
        self.assertTrue(
            any(
                "_handle_elicitation_request" in repr(task.get_coro())
                for task in asyncio.all_tasks()
                if not task.done()
            )
        )
        response_release.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if not any(
                "_handle_elicitation_request" in repr(task.get_coro())
                for task in asyncio.all_tasks()
                if not task.done()
            ):
                break
        self.assertFalse(
            any(
                "_handle_elicitation_request" in repr(task.get_coro())
                for task in asyncio.all_tasks()
                if not task.done()
            )
        )


class FakeStream:
    def __init__(self):
        self.frames = []
        self.close = AsyncMock()

    async def last_cursor(self):
        return 0

    async def emit(self, frame):
        self.frames.append(frame)


class FakeStateStore:
    def __init__(self, value=None, log=None):
        self.value = copy.deepcopy(value)
        self.log = log
        self.aclose = AsyncMock()

    async def get_item(self, key):
        if self.value is None:
            return None
        return SimpleNamespace(value=copy.deepcopy(self.value))

    async def set_item(self, key, value):
        self.value = copy.deepcopy(value)
        if self.log is not None:
            statuses = [entry.get("status") for entry in value.get("input_journal", [])]
            self.log.append(f"state:{','.join(statuses)}")


class FakeInvocationStore:
    def __init__(self):
        self.records = {}

    async def get(self, invocation_id):
        value = self.records.get(invocation_id)
        return copy.deepcopy(value)

    async def put(
        self,
        invocation_id,
        *,
        task_id,
        framework_input_id,
        status,
        task_status,
        payload=None,
    ):
        self.records[invocation_id] = {
            "task_id": task_id,
            "invocation_id": invocation_id,
            "framework_input_id": framework_input_id,
            "status": status,
            "task_status": task_status,
            "payload": payload,
        }


class QueueHarness:
    instances = []
    start_gate = None
    log = None

    def __init__(self):
        self.queue = asyncio.Queue()
        self.pending = set()
        self.accepting = True
        self.sent = []
        self.start = AsyncMock(side_effect=self._start)
        self.abort = AsyncMock(side_effect=self._abort)
        self.close = AsyncMock(side_effect=self._close)
        self.idle_seen = asyncio.Event()
        self.live_elicitation = False
        type(self).instances.append(self)

    async def _start(self, *args, **kwargs):
        if type(self).start_gate is not None:
            await type(self).start_gate.wait()

    async def send(self, prompt, *, mode=None, causal_idle=False):
        self.sent.append((prompt, mode))
        if type(self).log is not None:
            type(self).log.append(f"send:{prompt}")
        return "message"

    async def events(self):
        while True:
            item = await self.queue.get()
            if item is None:
                self.idle_seen.set()
                return
            yield item

    async def queue_input(self, input_id, prompt, mode):
        if not self.accepting:
            raise HarnessClosingError()
        request = NativeInputRequest(
            input_id, prompt, mode, asyncio.get_running_loop().create_future()
        )
        self.pending.add(request.acknowledged)
        await self.queue.put(request)
        try:
            return await request.acknowledged
        finally:
            self.pending.discard(request.acknowledged)

    async def queue_elicitation_decision(self, elicitation_id, action, content):
        if not self.accepting:
            raise HarnessClosingError()
        request = ElicitationDecisionRequest(
            elicitation_id,
            action,
            content,
            asyncio.get_running_loop().create_future(),
        )
        self.pending.add(request.acknowledged)
        await self.queue.put(request)
        try:
            return await request.acknowledged
        finally:
            self.pending.discard(request.acknowledged)

    def answer_elicitation(self, elicitation_id, action, content):
        return self.live_elicitation

    def bind_recovered_elicitations(self, markers):
        self.bound_markers = markers

    def discard_recovered_elicitation(self, elicitation_id):
        return None

    def stop_accepting_controls(self):
        self.accepting = False
        for pending in self.pending:
            if not pending.done():
                pending.set_exception(HarnessClosingError())

    async def _abort(self):
        return None

    async def _close(self):
        self.stop_accepting_controls()


class ImmediateHarness(QueueHarness):
    async def events(self):
        if False:
            yield None


class AgentTaskTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        agent._HARNESS_SLOTS.clear()
        agent._CLIENT_CANCEL_REQUESTED.clear()
        QueueHarness.instances.clear()
        QueueHarness.start_gate = None
        QueueHarness.log = None
        ImmediateHarness.log = None
        self.invocation_store = FakeInvocationStore()
        invocation_patch = patch.object(
            agent, "_INVOCATION_STORE", self.invocation_store
        )
        invocation_patch.start()
        self.addCleanup(invocation_patch.stop)

    def context(
        self,
        *,
        entry_mode="fresh",
        cancel=False,
        shutdown=False,
        cancel_requested=False,
        invocation_id="invocation",
        framework_input_id="framework-input",
        native_input_id=None,
        mode=None,
        prompt="initial",
    ):
        cancel_event = asyncio.Event()
        shutdown_event = asyncio.Event()
        if cancel:
            cancel_event.set()
        if shutdown:
            shutdown_event.set()
        task_input = {
            "invocation_id": invocation_id,
            "prompt": prompt,
            "session_id": "session",
        }
        if native_input_id is not None:
            task_input["input_id"] = native_input_id
        if mode is not None:
            task_input["mode"] = mode
        return SimpleNamespace(
            input=task_input,
            entry_mode=entry_mode,
            input_id=framework_input_id,
            recovery_count=1 if entry_mode == "recovered" else 0,
            cancel=cancel_event,
            shutdown=shutdown_event,
            cancel_requested=cancel_requested,
            exit_for_recovery=AsyncMock(return_value="deferred"),
        )

    async def run_task(
        self,
        *,
        context=None,
        state=None,
        harness=ImmediateHarness,
        restore=False,
        restore_side_effect=None,
        snapshot_side_effect=None,
        log=None,
        invocation_store=None,
    ):
        context = context or self.context()
        stream = FakeStream()
        state_store = FakeStateStore(state, log)
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=restore),
            save=AsyncMock(side_effect=snapshot_side_effect),
        )
        if restore_side_effect is not None:
            snapshot.restore.side_effect = restore_side_effect
        invocation_store = invocation_store or FakeInvocationStore()
        with patch.object(agent, "_CONFIG_ROOT", self.root / "config"), patch.object(
            agent, "_SNAPSHOT_STORE", snapshot
        ), patch.object(agent, "_INVOCATION_STORE", invocation_store), patch.object(
            agent, "CopilotHarness", harness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ), patch.object(
            agent, "_get_legacy_state_item", AsyncMock(return_value=None)
        ):
            result = await agent.copilot_agent._fn(context)
        return result, stream, state_store, snapshot

    async def test_missing_local_db_restores_on_resumed_entry(self):
        async def restore(_session_id, config_dir):
            config_dir.mkdir(parents=True)
            (config_dir / "session-store.db").write_bytes(b"db")
            return True

        await self.run_task(
            context=self.context(entry_mode="resumed"),
            state={"has_snapshot": True},
            restore_side_effect=restore,
        )
        harness = QueueHarness.instances[-1]
        self.assertTrue(harness.start.call_args.kwargs["recover"])

    async def test_promised_snapshot_missing_fails_instead_of_starting_fresh(self):
        with self.assertRaisesRegex(FileNotFoundError, "says a Copilot snapshot"):
            await self.run_task(
                state={"has_snapshot": True},
                invocation_store=self.invocation_store,
            )
        QueueHarness.instances[-1].start.assert_not_awaited()
        self.assertEqual(
            self.invocation_store.records["invocation"]["status"], "failed"
        )

    async def test_legacy_config_and_marker_migrate_before_fresh_fallback(self):
        config_root = self.root / "legacy-config-root"
        legacy = config_root / "session"
        legacy.mkdir(parents=True)
        (legacy / "session-store.db").write_bytes(b"legacy-db")
        (legacy / "session-state").mkdir()
        (legacy / "session-state" / "history").write_text(
            "legacy-history", encoding="utf-8"
        )
        new_store = FakeStateStore()
        legacy_store = FakeStateStore(
            {
                "pending_elicitation": {
                    "elicitation_id": "legacy-question",
                    "message": "Continue?",
                    "schema": {},
                    "decision": None,
                }
            }
        )
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False), save=AsyncMock()
        )
        stream = FakeStream()

        class StateStores:
            @classmethod
            async def get_or_create(cls, *args, **kwargs):
                return new_store

            def __new__(cls, name):
                self.assertEqual(name, "copilot-state-session")
                return legacy_store

        with patch.object(agent, "_CONFIG_ROOT", config_root), patch.object(
            agent, "_SNAPSHOT_STORE", snapshot
        ), patch.object(agent, "CopilotHarness", ImmediateHarness), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent, "FoundryStateStore", StateStores
        ):
            await agent.copilot_agent._fn(self.context())

        hashed = config_root / session_storage_key("session")
        self.assertEqual((hashed / "session-store.db").read_bytes(), b"legacy-db")
        self.assertEqual(
            (hashed / "session-state" / "history").read_text(encoding="utf-8"),
            "legacy-history",
        )
        self.assertTrue((legacy / "session-store.db").exists())
        snapshot.restore.assert_not_awaited()
        harness = ImmediateHarness.instances[-1]
        self.assertTrue(harness.start.call_args.kwargs["recover"])
        self.assertEqual(
            new_store.value["pending_elicitation"]["elicitation_id"],
            "legacy-question",
        )
        legacy_store.aclose.assert_awaited_once()

    async def test_legacy_marker_migrates_after_config_was_already_copied(self):
        config_root = self.root / "partial-migration-root"
        hashed = config_root / session_storage_key("session")
        hashed.mkdir(parents=True)
        (hashed / "session-store.db").write_bytes(b"already-copied")
        new_store = FakeStateStore()
        legacy_store = FakeStateStore(
            {
                "pending_elicitation": {
                    "elicitation_id": "legacy-question",
                    "message": "Continue?",
                    "schema": {},
                    "decision": None,
                }
            }
        )
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False), save=AsyncMock()
        )
        stream = FakeStream()

        class StateStores:
            @classmethod
            async def get_or_create(cls, *args, **kwargs):
                return new_store

            def __new__(cls, name):
                self.assertEqual(name, "copilot-state-session")
                return legacy_store

        with patch.object(agent, "_CONFIG_ROOT", config_root), patch.object(
            agent, "_SNAPSHOT_STORE", snapshot
        ), patch.object(agent, "CopilotHarness", ImmediateHarness), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent, "FoundryStateStore", StateStores
        ):
            await agent.copilot_agent._fn(self.context())

        snapshot.restore.assert_not_awaited()
        self.assertEqual(
            new_store.value["pending_elicitation"]["elicitation_id"],
            "legacy-question",
        )
        self.assertTrue(
            ImmediateHarness.instances[-1].start.call_args.kwargs["recover"]
        )
        legacy_store.aclose.assert_awaited_once()

    async def test_shutdown_defers_without_closing_stream_or_failure_frame(self):
        class StopHarness(QueueHarness):
            async def events(self):
                while not (self.abort.await_count):
                    await asyncio.sleep(0)
                if False:
                    yield None

        shutdown = asyncio.Event()
        shutdown.set()
        context = TaskContext(
            task_id="copilot-session",
            session_id="session",
            input={
                "invocation_id": "invocation",
                "prompt": "initial",
                "session_id": "session",
            },
            recovery_count=1,
            entry_mode="recovered",
            shutdown=shutdown,
        )
        result, stream, _, snapshot = await self.run_task(
            context=context,
            harness=StopHarness,
            invocation_store=self.invocation_store,
        )
        self.assertEqual(type(result).__name__, "_ExitForRecovery")
        stream.close.assert_not_awaited()
        self.assertNotIn("turn_failed", [frame["type"] for frame in stream.frames])
        snapshot.save.assert_awaited()
        self.assertEqual(
            self.invocation_store.records["invocation"]["status"], "running"
        )

    async def test_explicit_cancel_is_not_resurrected(self):
        class StopHarness(QueueHarness):
            async def events(self):
                while not self.abort.await_count:
                    await asyncio.sleep(0)
                if False:
                    yield None

        context = self.context(cancel=True, shutdown=True)
        agent.mark_client_cancel("session")
        _, stream, _, _ = await self.run_task(
            context=context,
            harness=StopHarness,
            invocation_store=self.invocation_store,
        )
        context.exit_for_recovery.assert_not_awaited()
        self.assertIn("cancelled", [frame["type"] for frame in stream.frames])
        stream.close.assert_awaited_once()
        self.assertEqual(
            self.invocation_store.records["invocation"]["status"], "cancelled"
        )

    async def test_native_input_waits_for_ready_and_is_durable_before_202(self):
        log = []
        QueueHarness.start_gate = asyncio.Event()
        QueueHarness.log = log
        context = self.context()
        with patch.object(agent, "_CONFIG_ROOT", self.root / "config"):
            slot = agent.reserve_harness("session")
        self.assertFalse(slot.ready.done())

        stream = FakeStream()
        state_store = FakeStateStore({}, log)
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False),
            save=AsyncMock(side_effect=lambda *args, **kwargs: log.append("snapshot")),
        )
        with patch.object(agent, "_CONFIG_ROOT", self.root / "config"), patch.object(
            agent, "_SNAPSHOT_STORE", snapshot
        ), patch.object(agent, "CopilotHarness", QueueHarness), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(context))
            submit = asyncio.create_task(
                agent.submit_native_input(
                    "session", "input-1", "follow up", "immediate"
                )
            )
            await asyncio.sleep(0)
            self.assertFalse(submit.done())
            config_dir = self.root / "config" / session_storage_key("session")
            workspace = config_dir / "session-state" / "session"
            workspace.mkdir(parents=True)
            sqlite3.connect(config_dir / "session-store.db").close()
            sqlite3.connect(workspace / "session.db").close()
            QueueHarness.start_gate.set()
            result = await asyncio.wait_for(submit, 2)
            self.assertEqual(result["status"], "delivered")
            harness = QueueHarness.instances[-1]
            self.assertLess(log.index("state:accepted"), log.index("send:follow up"))
            self.assertLess(log.index("send:follow up"), log.index("snapshot"))
            duplicate = await agent.submit_native_input(
                "session", "input-1", "follow up", "immediate"
            )
            self.assertTrue(duplicate["deduplicated"])
            with self.assertRaisesRegex(ValueError, "different prompt"):
                await agent.submit_native_input(
                    "session", "input-1", "different", "immediate"
                )
            with self.assertRaisesRegex(ValueError, "different prompt or mode"):
                await agent.submit_native_input(
                    "session", "input-1", "follow up", "enqueue"
                )
            with self.assertRaisesRegex(ValueError, "exceed 512 KiB"):
                await agent.submit_native_input(
                    "session", "too-large", "x" * (513 * 1024), "enqueue"
                )
            self.assertFalse(task.done())
            await harness.queue.put(None)
            await asyncio.wait_for(task, 2)
            self.assertEqual(state_store.value["input_journal"], [])
            self.assertIsNone(
                await agent.submit_native_input(
                    "session", "after-close", "later", "enqueue"
                )
            )

    async def test_initial_input_is_reserved_before_ready_and_retries_deduplicate(self):
        log = []
        QueueHarness.start_gate = asyncio.Event()
        QueueHarness.log = log
        state_store = FakeStateStore({}, log)
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False),
            save=AsyncMock(side_effect=lambda *args, **kwargs: log.append("snapshot")),
        )
        stream = FakeStream()
        context = self.context(
            native_input_id="initial-id",
            prompt="initial prompt",
            mode="immediate",
        )
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-initial-reservation"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", QueueHarness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ), patch.object(
            agent, "_get_legacy_state_item", AsyncMock(return_value=None)
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(context))
            while "input_journal" not in (state_store.value or {}):
                await asyncio.sleep(0)
            record = state_store.value["input_journal"][0]
            self.assertEqual(
                record,
                {
                    "input_id": "initial-id",
                    "prompt": "initial prompt",
                    "mode": "immediate",
                    "status": "accepted",
                },
            )
            retry_before_ready = asyncio.create_task(
                agent.submit_native_input(
                    "session", "initial-id", "initial prompt", "immediate"
                )
            )
            await asyncio.sleep(0)
            self.assertFalse(retry_before_ready.done())
            QueueHarness.start_gate.set()
            before_receipt = await asyncio.wait_for(retry_before_ready, 2)
            self.assertEqual(
                before_receipt,
                {
                    "status": "delivered",
                    "input_id": "initial-id",
                    "deduplicated": True,
                },
            )
            harness = QueueHarness.instances[-1]
            self.assertEqual(harness.sent, [("initial prompt", "immediate")])
            snapshot.save.assert_not_awaited()
            self.assertNotIn("has_snapshot", state_store.value)
            after_receipt = await agent.submit_native_input(
                "session", "initial-id", "initial prompt", "immediate"
            )
            self.assertEqual(after_receipt, before_receipt)
            self.assertEqual(harness.sent, [("initial prompt", "immediate")])

            for prompt, mode in (
                ("different prompt", "immediate"),
                ("initial prompt", "enqueue"),
            ):
                with self.subTest(prompt=prompt, mode=mode), self.assertRaisesRegex(
                    ValueError, "different prompt or mode"
                ):
                    await agent.submit_native_input(
                        "session", "initial-id", prompt, mode
                    )
            self.assertEqual(
                state_store.value["input_journal"][0]["prompt"],
                "initial prompt",
            )
            self.assertEqual(
                state_store.value["input_journal"][0]["mode"],
                "immediate",
            )
            self.assertEqual(harness.sent, [("initial prompt", "immediate")])
            early_followup = await agent.submit_native_input(
                "session", "early-followup", "follow up", "enqueue"
            )
            self.assertEqual(early_followup["status"], "delivered")
            self.assertEqual(
                harness.sent,
                [
                    ("initial prompt", "immediate"),
                    ("follow up", "enqueue"),
                ],
            )
            snapshot.save.assert_not_awaited()
            self.assertNotIn("has_snapshot", state_store.value)

            config_dir = Path(harness.start.call_args.kwargs["config_directory"])
            workspace = config_dir / "session-state" / "session"
            workspace.mkdir(parents=True)
            sqlite3.connect(config_dir / "session-store.db").close()
            sqlite3.connect(workspace / "session.db").close()
            checkpoint_ack = asyncio.get_running_loop().create_future()
            await harness.queue.put(
                TodoCheckpointRequest("startup-ready", checkpoint_ack)
            )
            await asyncio.wait_for(checkpoint_ack, 2)
            self.assertTrue(state_store.value["has_snapshot"])
            self.assertEqual(snapshot.save.await_count, 1)
            await harness.queue.put(None)
            await task
            self.assertEqual(snapshot.save.await_count, 2)

    async def test_initial_delivery_uses_only_final_snapshot_after_late_db_creation(
        self,
    ):
        QueueHarness.start_gate = asyncio.Event()
        state_store = FakeStateStore({})
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False),
            save=AsyncMock(),
        )
        stream = FakeStream()
        context = self.context(
            native_input_id="initial-id",
            prompt="initial prompt",
            mode="enqueue",
        )
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-final-only"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", QueueHarness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ), patch.object(
            agent, "_get_legacy_state_item", AsyncMock(return_value=None)
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(context))
            while "input_journal" not in (state_store.value or {}):
                await asyncio.sleep(0)
            retry = asyncio.create_task(
                agent.submit_native_input(
                    "session", "initial-id", "initial prompt", "enqueue"
                )
            )
            QueueHarness.start_gate.set()
            self.assertTrue((await asyncio.wait_for(retry, 2))["deduplicated"])
            harness = QueueHarness.instances[-1]
            snapshot.save.assert_not_awaited()
            self.assertNotIn("has_snapshot", state_store.value)

            config_dir = Path(harness.start.call_args.kwargs["config_directory"])
            workspace = config_dir / "session-state" / "session"
            workspace.mkdir(parents=True)
            sqlite3.connect(config_dir / "session-store.db").close()
            sqlite3.connect(workspace / "session.db").close()
            await harness.queue.put(None)
            await task
            snapshot.save.assert_awaited_once_with("session", config_dir, live=True)
            self.assertTrue(state_store.value["has_snapshot"])

    async def test_final_checkpoint_preserves_committed_wal_with_a_writer_remaining(
        self,
    ):
        config = self.root / "config" / session_storage_key("session")
        workspace = config / "session-state" / "session"
        workspace.mkdir(parents=True)
        root_db = sqlite3.connect(config / "session-store.db")
        root_db.execute("CREATE TABLE sessions (id TEXT)")
        root_db.commit()
        root_db.close()
        writer = sqlite3.connect(workspace / "session.db")
        self.addCleanup(writer.close)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE proof (value TEXT)")
        writer.execute("INSERT INTO proof VALUES ('committed-in-wal')")
        writer.commit()
        self.assertTrue((workspace / "session.db-wal").exists())
        snapshots = SessionSnapshotStore(self.root / "final-snapshots")
        snapshots._use_state_store = False

        _, _, _, snapshot = await self.run_task(snapshot_side_effect=snapshots.save)
        snapshot.save.assert_awaited_once_with("session", config, live=True)
        restored = self.root / "restored-final"
        self.assertTrue(await snapshots.restore("session", restored))
        restored_db = sqlite3.connect(
            restored / "session-state" / "session" / "session.db"
        )
        self.addCleanup(restored_db.close)
        self.assertEqual(
            restored_db.execute("SELECT value FROM proof").fetchall(),
            [("committed-in-wal",)],
        )

    async def test_crash_before_first_database_keeps_journal_without_snapshot_promise(
        self,
    ):
        QueueHarness.start_gate = asyncio.Event()
        state_store = FakeStateStore({})
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False),
            save=AsyncMock(),
        )
        stream = FakeStream()
        context = self.context(
            native_input_id="initial-id",
            prompt="initial prompt",
            mode="enqueue",
        )
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-crash-before-db"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", QueueHarness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ), patch.object(
            agent, "_get_legacy_state_item", AsyncMock(return_value=None)
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(context))
            QueueHarness.start_gate.set()
            while not QueueHarness.instances:
                await asyncio.sleep(0)
            harness = QueueHarness.instances[-1]
            while (
                len(harness.sent) != 1
                or state_store.value["input_journal"][0]["status"] != "delivered"
            ):
                await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            snapshot.save.assert_not_awaited()
            self.assertNotIn("has_snapshot", state_store.value)
            self.assertEqual(
                state_store.value["input_journal"][0]["status"], "delivered"
            )

        recovery_state = copy.deepcopy(state_store.value)
        ImmediateHarness.instances.clear()
        await self.run_task(
            context=self.context(
                entry_mode="recovered",
                native_input_id="initial-id",
                prompt="initial prompt",
                mode="enqueue",
            ),
            state=recovery_state,
            restore=False,
        )
        recovered_harness = ImmediateHarness.instances[-1]
        self.assertFalse(recovered_harness.start.call_args.kwargs["recover"])
        self.assertEqual(
            recovered_harness.sent,
            [("initial prompt", "enqueue")],
        )

    async def test_promised_snapshot_missing_db_fails_delivery_without_new_receipt(
        self,
    ):
        config_root = self.root / "config-promised-strict"
        config_dir = config_root / session_storage_key("session")
        config_dir.mkdir(parents=True)
        (config_dir / "session-store.db").write_bytes(b"local-root-db")

        snapshot = SessionSnapshotStore(self.root / "strict-snapshots")
        snapshot._use_state_store = False
        previous_source = self.root / "previous-source"
        previous_source.mkdir()
        (previous_source / "session-store.db").write_bytes(b"previous")
        previous_blob = _pack_dir(previous_source)
        snapshot._path("session").write_bytes(previous_blob)

        record = {
            "input_id": "initial-id",
            "prompt": "initial prompt",
            "mode": "enqueue",
            "status": "accepted",
        }
        state_store = FakeStateStore(
            {
                "has_snapshot": True,
                "input_journal": [record],
            }
        )
        stream = FakeStream()
        with patch.object(agent, "_CONFIG_ROOT", config_root), patch.object(
            agent, "_SNAPSHOT_STORE", snapshot
        ), patch.object(agent, "CopilotHarness", ImmediateHarness), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ), patch.object(
            agent, "_get_legacy_state_item", AsyncMock(return_value=None)
        ):
            with self.assertRaisesRegex(
                FileNotFoundError, "required Copilot recovery database"
            ):
                await agent.copilot_agent._fn(
                    self.context(
                        native_input_id="initial-id",
                        prompt="initial prompt",
                        mode="enqueue",
                    )
                )

        self.assertEqual(snapshot._path("session").read_bytes(), previous_blob)
        persisted = state_store.value["input_journal"][0]
        self.assertEqual(persisted["status"], "accepted")
        self.assertNotIn("receipt", persisted)
        self.assertEqual(
            [frame["type"] for frame in stream.frames],
            ["turn_start", "turn_failed"],
        )

    async def test_idle_queued_during_acceptance_does_not_cover_native_input(self):
        harness = CopilotHarness()
        idle = SimpleNamespace(type=SessionEventType.SESSION_IDLE)

        class Session:
            abort = AsyncMock()

            async def send(self, prompt, *, mode=None):
                return f"message-{prompt}"

        harness.session = Session()
        harness.start = AsyncMock()
        stream = FakeStream()
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False), save=AsyncMock()
        )

        class IdleInjectingStateStore(FakeStateStore):
            def __init__(self):
                super().__init__({})
                self.injected = False

            async def set_item(self, key, value):
                await super().set_item(key, value)
                statuses = [
                    entry.get("status") for entry in value.get("input_journal", [])
                ]
                if statuses == ["accepted"] and not self.injected:
                    self.injected = True
                    harness._on_event(idle)

        state_store = IdleInjectingStateStore()
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-idle"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", return_value=harness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(self.context()))
            while not harness.start.await_count:
                await asyncio.sleep(0)
            result = await agent.submit_native_input(
                "session", "input-idle", "follow up", "enqueue"
            )
            self.assertEqual(result["status"], "delivered")
            self.assertFalse(task.done())
            self.assertEqual(
                state_store.value["input_journal"][0]["status"], "delivered"
            )
            harness._on_event(idle)
            await asyncio.wait_for(task, 2)
            self.assertEqual(state_store.value["input_journal"], [])

    async def test_during_close_routes_away_from_the_old_harness(self):
        class ClosingHarness(QueueHarness):
            close_started = None
            close_gate = None

            async def _close(self):
                type(self).close_started.set()
                await type(self).close_gate.wait()
                self.stop_accepting_controls()

        ClosingHarness.close_started = asyncio.Event()
        ClosingHarness.close_gate = asyncio.Event()
        stream = FakeStream()
        state_store = FakeStateStore({})
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False), save=AsyncMock()
        )
        with patch.object(agent, "_CONFIG_ROOT", self.root / "config"), patch.object(
            agent, "_SNAPSHOT_STORE", snapshot
        ), patch.object(agent, "CopilotHarness", ClosingHarness), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(self.context()))
            while not ClosingHarness.instances:
                await asyncio.sleep(0)
            harness = ClosingHarness.instances[-1]
            while not harness.start.await_count:
                await asyncio.sleep(0)
            await harness.queue.put(None)
            await ClosingHarness.close_started.wait()
            self.assertIsNone(
                await agent.submit_native_input(
                    "session", "during-close", "later", "enqueue"
                )
            )
            ClosingHarness.close_gate.set()
            await task

    async def test_normal_completion_leaves_no_stop_watcher_tasks(self):
        await self.run_task()
        await asyncio.sleep(0)
        pending = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
            and not task.done()
            and "watch_stop" in repr(task.get_coro())
        ]
        self.assertEqual(pending, [])

    async def test_sequential_turns_keep_independent_invocation_status(self):
        statuses = FakeInvocationStore()
        await self.run_task(
            context=self.context(invocation_id="old-invocation"),
            invocation_store=statuses,
        )
        self.assertEqual(statuses.records["old-invocation"]["status"], "completed")

        QueueHarness.instances.clear()
        new_turn = asyncio.create_task(
            self.run_task(
                context=self.context(invocation_id="new-invocation"),
                harness=QueueHarness,
                invocation_store=statuses,
            )
        )
        while not QueueHarness.instances:
            await asyncio.sleep(0)
        harness = QueueHarness.instances[-1]
        while not harness.start.await_count:
            await asyncio.sleep(0)

        self.assertEqual(statuses.records["old-invocation"]["status"], "completed")
        self.assertEqual(statuses.records["new-invocation"]["status"], "running")
        await harness.queue.put(None)
        await asyncio.wait_for(new_turn, 2)
        self.assertEqual(statuses.records["old-invocation"]["status"], "completed")
        self.assertEqual(statuses.records["new-invocation"]["status"], "completed")

    async def test_second_question_during_first_snapshot_keeps_both_ids(self):
        state = {
            "pending_elicitation": {
                "elicitation_id": "question-1",
                "message": "First?",
                "schema": {},
                "decision": None,
            }
        }
        stream = FakeStream()
        state_store = FakeStateStore(state)
        question_2_ack = asyncio.get_running_loop().create_future()
        injected = False

        async def save(_session_id, _config_dir, *, live=False):
            nonlocal injected
            if live and not injected:
                injected = True
                await QueueHarness.instances[-1].queue.put(
                    ElicitationRequest(
                        "question-2",
                        "Second?",
                        {},
                        question_2_ack,
                    )
                )

        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False),
            save=AsyncMock(side_effect=save),
        )
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-two-questions"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", QueueHarness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(self.context()))
            while not QueueHarness.instances:
                await asyncio.sleep(0)
            harness = QueueHarness.instances[-1]
            while not harness.start.await_count:
                await asyncio.sleep(0)
            result = await agent.submit_elicitation_decision(
                "session", "question-1", "accept", {}
            )
            self.assertEqual(result["status"], "delivered_as_message")
            await asyncio.wait_for(question_2_ack, 2)
            sent_count = len(harness.sent)
            self.assertEqual(
                await agent.submit_elicitation_decision(
                    "session", "question-1", "accept", {}
                ),
                result,
            )
            self.assertEqual(len(harness.sent), sent_count)
            markers = state_store.value["elicitations"]
            self.assertEqual(markers["question-1"]["delivery"], "submitted")
            self.assertIsNone(markers["question-2"]["decision"])
            self.assertEqual(
                state_store.value["pending_elicitation"]["elicitation_id"],
                "question-2",
            )
            await harness.queue.put(None)
            await asyncio.wait_for(task, 2)
            markers = state_store.value["elicitations"]
            self.assertNotIn("question-1", markers)
            self.assertIn("question-2", markers)

    async def test_todo_checkpoint_does_not_confirm_blocked_hitl_response(self):
        state = {
            "pending_elicitation": {
                "elicitation_id": "question-1",
                "message": "Continue?",
                "schema": {},
                "decision": None,
            }
        }
        stream = FakeStream()
        state_store = FakeStateStore(state)
        checkpoint_ack = asyncio.get_running_loop().create_future()
        injected = False

        async def save(_session_id, _config_dir, *, live=False):
            nonlocal injected
            if live and not injected:
                injected = True
                await QueueHarness.instances[-1].queue.put(
                    TodoCheckpointRequest("parallel-tool", checkpoint_ack)
                )

        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False),
            save=AsyncMock(side_effect=save),
        )
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-hitl-checkpoint"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", QueueHarness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(self.context()))
            while not QueueHarness.instances:
                await asyncio.sleep(0)
            harness = QueueHarness.instances[-1]
            while not harness.start.await_count:
                await asyncio.sleep(0)
            result = await agent.submit_elicitation_decision(
                "session", "question-1", "accept", {}
            )
            self.assertEqual(result["status"], "delivered_as_message")
            await asyncio.wait_for(checkpoint_ack, 2)
            self.assertEqual(
                state_store.value["elicitations"]["question-1"]["delivery"],
                "submitted",
            )
            await harness.queue.put(None)
            await asyncio.wait_for(task, 2)
            self.assertNotIn("question-1", state_store.value["elicitations"])

    async def test_recovery_replays_uncovered_accepted_inputs(self):
        state = {
            "input_journal": [
                {
                    "input_id": "accepted",
                    "prompt": "accepted prompt",
                    "mode": "enqueue",
                    "status": "delivered",
                }
            ]
        }

        async def restore(_session_id, config_dir):
            workspace = config_dir / "session-state" / "session"
            workspace.mkdir(parents=True)
            (config_dir / "session-store.db").write_bytes(b"db")
            (workspace / "session.db").write_bytes(b"db")
            return True

        _, _, _, snapshot = await self.run_task(
            context=self.context(
                entry_mode="recovered",
                native_input_id="accepted",
                mode="enqueue",
                prompt="accepted prompt",
            ),
            state=state,
            restore_side_effect=restore,
        )
        harness = ImmediateHarness.instances[-1]
        self.assertEqual(harness.sent, [("accepted prompt", "enqueue")])
        self.assertEqual(snapshot.save.await_count, 2)

    async def test_recovery_replays_initial_record_only_once_for_each_status(self):
        for status in ("accepted", "delivered"):
            with self.subTest(status=status):
                agent._HARNESS_SLOTS.clear()
                ImmediateHarness.instances.clear()
                record = {
                    "input_id": "initial-id",
                    "prompt": "initial prompt",
                    "mode": "enqueue",
                    "status": status,
                }
                if status == "delivered":
                    record["receipt"] = {
                        "status": "delivered",
                        "input_id": "initial-id",
                    }
                state = {"input_journal": [record]}

                async def restore(_session_id, config_dir):
                    workspace = config_dir / "session-state" / "session"
                    workspace.mkdir(parents=True)
                    (config_dir / "session-store.db").write_bytes(b"db")
                    (workspace / "session.db").write_bytes(b"db")
                    return True

                _, _, _, snapshot = await self.run_task(
                    context=self.context(
                        entry_mode="recovered",
                        native_input_id="initial-id",
                        prompt="initial prompt",
                        mode="enqueue",
                    ),
                    state=state,
                    restore_side_effect=restore,
                )
                self.assertEqual(
                    ImmediateHarness.instances[-1].sent,
                    [("initial prompt", "enqueue")],
                )
                self.assertEqual(snapshot.save.await_count, 2)

    async def test_existing_accepted_input_rejects_prompt_and_mode_conflicts(self):
        state = {
            "input_journal": [
                {
                    "input_id": "accepted",
                    "prompt": "original",
                    "mode": "enqueue",
                    "status": "accepted",
                }
            ]
        }
        for prompt, mode in (("different", "enqueue"), ("original", "immediate")):
            with self.subTest(prompt=prompt, mode=mode):
                agent._HARNESS_SLOTS.clear()
                ImmediateHarness.instances.clear()
                with self.assertRaisesRegex(ValueError, "different prompt or mode"):
                    await self.run_task(
                        context=self.context(
                            native_input_id="accepted",
                            prompt=prompt,
                            mode=mode,
                        ),
                        state=state,
                    )
                self.assertEqual(ImmediateHarness.instances[-1].sent, [])

    async def test_recovered_hitl_decisions_remain_until_idle_and_keep_empty_accept(
        self,
    ):
        for action, content in (
            ("accept", {}),
            ("decline", None),
            ("cancel", None),
        ):
            with self.subTest(action=action):
                agent._HARNESS_SLOTS.clear()
                QueueHarness.instances.clear()
                state = {
                    "pending_elicitation": {
                        "elicitation_id": "elicitation-1",
                        "message": "Continue?",
                        "schema": {},
                        "decision": None,
                    }
                }
                stream = FakeStream()
                state_store = FakeStateStore(state)
                snapshot = SimpleNamespace(
                    restore=AsyncMock(return_value=False), save=AsyncMock()
                )
                with patch.object(
                    agent, "_CONFIG_ROOT", self.root / f"config-{action}"
                ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
                    agent, "CopilotHarness", QueueHarness
                ), patch.object(
                    agent.streams, "get_or_create", AsyncMock(return_value=stream)
                ), patch.object(
                    agent.FoundryStateStore,
                    "get_or_create",
                    AsyncMock(return_value=state_store),
                ):
                    task = asyncio.create_task(agent.copilot_agent._fn(self.context()))
                    while not QueueHarness.instances:
                        await asyncio.sleep(0)
                    harness = QueueHarness.instances[-1]
                    while not harness.start.await_count:
                        await asyncio.sleep(0)
                    with self.assertRaisesRegex(ValueError, "does not match"):
                        await agent.submit_elicitation_decision(
                            "session", "stale", action, content
                        )
                    result = await agent.submit_elicitation_decision(
                        "session", "elicitation-1", action, content
                    )
                    self.assertIn(
                        result["status"], {"answered", "delivered_as_message"}
                    )
                    payload = json.loads(harness.sent[-1][0].split("] ", 1)[1])
                    self.assertEqual(payload["action"], action)
                    if action == "accept":
                        self.assertEqual(payload["content"], {})
                    sent_count = len(harness.sent)
                    duplicate = await agent.submit_elicitation_decision(
                        "session", "elicitation-1", action, content
                    )
                    self.assertEqual(duplicate, result)
                    self.assertEqual(len(harness.sent), sent_count)
                    conflicting_action = "decline" if action == "accept" else "accept"
                    with self.assertRaisesRegex(
                        ValueError, "different action or content"
                    ):
                        await agent.submit_elicitation_decision(
                            "session",
                            "elicitation-1",
                            conflicting_action,
                            {} if conflicting_action == "accept" else None,
                        )
                    self.assertEqual(len(harness.sent), sent_count)
                    self.assertEqual(
                        state_store.value["pending_elicitation"]["delivery"],
                        "submitted",
                    )
                    await harness.queue.put(None)
                    await task
                    self.assertIsNone(state_store.value["pending_elicitation"])

    async def test_recovered_submitted_decision_retry_is_deduplicated(self):
        receipt = {
            "status": "delivered_as_message",
            "elicitation_id": "elicitation-1",
        }
        state = {
            "pending_elicitation": {
                "elicitation_id": "elicitation-1",
                "message": "Continue?",
                "schema": {},
                "decision": {"action": "accept", "content": {}},
                "delivery": "submitted",
                "receipt": receipt,
            }
        }
        stream = FakeStream()
        state_store = FakeStateStore(state)
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False), save=AsyncMock()
        )
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-recovered-submitted"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", QueueHarness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ):
            task = asyncio.create_task(
                agent.copilot_agent._fn(self.context(entry_mode="recovered"))
            )
            while not QueueHarness.instances:
                await asyncio.sleep(0)
            harness = QueueHarness.instances[-1]
            while not harness.start.await_count:
                await asyncio.sleep(0)
            while len(harness.sent) < 2:
                await asyncio.sleep(0)
            sent_count = len(harness.sent)
            duplicate = await agent.submit_elicitation_decision(
                "session", "elicitation-1", "accept", {}
            )
            self.assertEqual(duplicate, receipt)
            self.assertEqual(len(harness.sent), sent_count)
            with self.assertRaisesRegex(ValueError, "different action or content"):
                await agent.submit_elicitation_decision(
                    "session", "elicitation-1", "decline", None
                )
            self.assertEqual(len(harness.sent), sent_count)
            await harness.queue.put(None)
            await task

    async def test_decision_dedupe_preserves_json_types_and_dict_key_order(self):
        markers = {
            question: {
                "elicitation_id": question,
                "message": question,
                "schema": {},
                "decision": None,
            }
            for question in ("bool-first", "int-first", "nested", "key-order")
        }
        state = {
            "elicitations": markers,
            "pending_elicitation": markers["key-order"],
        }
        stream = FakeStream()
        state_store = FakeStateStore(state)
        snapshot = SimpleNamespace(
            restore=AsyncMock(return_value=False), save=AsyncMock()
        )
        with patch.object(
            agent, "_CONFIG_ROOT", self.root / "config-json-types"
        ), patch.object(agent, "_SNAPSHOT_STORE", snapshot), patch.object(
            agent, "CopilotHarness", QueueHarness
        ), patch.object(
            agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ):
            task = asyncio.create_task(agent.copilot_agent._fn(self.context()))
            while not QueueHarness.instances:
                await asyncio.sleep(0)
            harness = QueueHarness.instances[-1]
            while not harness.start.await_count:
                await asyncio.sleep(0)

            cases = (
                ("bool-first", {"value": True}, {"value": 1}),
                ("int-first", {"value": 1}, {"value": True}),
                (
                    "nested",
                    {"items": [{"value": True}]},
                    {"items": [{"value": 1}]},
                ),
            )
            for question, accepted, conflicting in cases:
                receipt = await agent.submit_elicitation_decision(
                    "session", question, "accept", accepted
                )
                sent_count = len(harness.sent)
                self.assertEqual(
                    await agent.submit_elicitation_decision(
                        "session", question, "accept", accepted
                    ),
                    receipt,
                )
                self.assertEqual(len(harness.sent), sent_count)
                with self.assertRaisesRegex(ValueError, "different action or content"):
                    await agent.submit_elicitation_decision(
                        "session", question, "accept", conflicting
                    )
                self.assertEqual(len(harness.sent), sent_count)

            receipt = await agent.submit_elicitation_decision(
                "session",
                "key-order",
                "accept",
                {"first": 1, "second": "two"},
            )
            sent_count = len(harness.sent)
            self.assertEqual(
                await agent.submit_elicitation_decision(
                    "session",
                    "key-order",
                    "accept",
                    {"second": "two", "first": 1},
                ),
                receipt,
            )
            self.assertEqual(len(harness.sent), sent_count)
            self.assertEqual(set(state_store.value["elicitations"]), set(markers))
            await harness.queue.put(None)
            await task

    def test_crash_hook_is_disabled_for_recovered_entry(self):
        with patch.object(agent, "_SIMULATE_CRASH_AFTER_EVENTS", 1), patch.object(
            agent.os, "_exit"
        ) as exit_mock:
            agent._maybe_crash(5, enabled=False)
            exit_mock.assert_not_called()
            agent._maybe_crash(1, enabled=True)
            exit_mock.assert_called_once_with(1)


class StartupEnvironmentTests(unittest.TestCase):
    def test_dotenv_is_loaded_before_environment_dependent_local_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "FOUNDRY_PROJECT_ENDPOINT=https://example.test\n"
                "SIMULATE_CRASH_AFTER_EVENTS=7\n",
                encoding="utf-8",
            )
            script = (
                "import sys;"
                f"sys.path.insert(0, {str(SRC)!r});"
                "import main,agent;"
                "print(agent._SNAPSHOT_STORE._use_state_store,"
                "agent._SIMULATE_CRASH_AFTER_EVENTS)"
            )
            env = os.environ.copy()
            env.pop("FOUNDRY_PROJECT_ENDPOINT", None)
            env.pop("SIMULATE_CRASH_AFTER_EVENTS", None)
            env["AGENTSERVER_STATE_ROOT"] = str(root / "state")
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        self.assertIn("True 7", result.stdout)


class HttpValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        agent._HARNESS_SLOTS.clear()
        self.addCleanup(agent._HARNESS_SLOTS.clear)

    @staticmethod
    def request(
        body=None,
        *,
        session_id="session",
        invocation_id="invocation",
        method="POST",
        accept=None,
    ):
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {
                "type": "http.request",
                "body": json.dumps(body).encode(),
                "more_body": False,
            }

        request = main.Request(
            {
                "type": "http",
                "method": method,
                "path": "/invocations",
                "query_string": b"",
                "headers": ([(b"accept", accept.encode("ascii"))] if accept else []),
            },
            receive,
        )
        request.state.session_id = session_id
        request.state.invocation_id = invocation_id
        request.state.call_id = "call"
        return request

    async def test_invalid_http_session_id_returns_standard_400(self):
        response = await main.handle_invoke(
            self.request({"input": "hello"}, session_id="../escape")
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["error"], "invalid_request")

    async def test_non_string_prompt_aliases_are_rejected_before_submission(self):
        with patch.object(
            main, "submit_native_input", AsyncMock()
        ) as submit, patch.object(main.copilot_agent, "start", AsyncMock()) as start:
            for field in ("input", "prompt", "message", "query"):
                for value in (None, 0, False, [], {}):
                    with self.subTest(field=field, value=value):
                        response = await main.handle_invoke(
                            self.request({field: value}, session_id="session")
                        )
                        self.assertEqual(response.status_code, 400)
            submit.assert_not_awaited()
            start.assert_not_awaited()

    async def test_legitimate_string_prompt_aliases_are_preserved(self):
        for field in ("input", "prompt", "message", "query"):
            with self.subTest(field=field), patch.object(
                main,
                "submit_native_input",
                AsyncMock(return_value={"status": "delivered"}),
            ) as submit:
                response = await main.handle_invoke(
                    self.request({field: "  hello  "}, session_id="session")
                )
                self.assertEqual(response.status_code, 202)
                self.assertEqual(submit.call_args.args[2], "hello")

    async def test_explicit_invalid_input_ids_are_rejected_not_regenerated(self):
        with patch.object(main.copilot_agent, "start", AsyncMock()) as start:
            for value in ("", None, 0, False):
                with self.subTest(value=value):
                    response = await main.handle_invoke(
                        self.request(
                            {"input": "hello", "input_id": value},
                            session_id="session",
                        )
                    )
                    self.assertEqual(response.status_code, 400)
            start.assert_not_awaited()

    async def test_absent_input_id_is_generated_once(self):
        generated = uuid.UUID("00000000-0000-0000-0000-000000000123")
        stream = SimpleNamespace()
        with patch.object(main.uuid, "uuid4", return_value=generated), patch.object(
            main, "submit_native_input", AsyncMock(return_value=None)
        ), patch.object(
            main.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            main.copilot_agent, "start", AsyncMock()
        ) as start, patch.object(
            main, "reserve_harness"
        ):
            response = await main.handle_invoke(
                self.request({"input": "hello"}, session_id="session")
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            start.call_args.kwargs["input"]["input_id"],
            str(generated),
        )

    async def test_elicitation_rejects_non_string_session_ids_without_routing(self):
        with patch.object(main, "submit_elicitation_decision", AsyncMock()) as submit:
            for value in (None, 123, False, ["session"], {"session": "id"}):
                with self.subTest(value=value):
                    response = await main.handle_elicit(
                        self.request(
                            {
                                "session_id": value,
                                "elicitation_id": "question",
                                "action": "accept",
                            }
                        )
                    )
                    self.assertEqual(response.status_code, 400)
            submit.assert_not_awaited()

    async def test_elicitation_preserves_literal_valid_string_session_ids(self):
        for session_id in ("session", "None", "123"):
            with self.subTest(session_id=session_id), patch.object(
                main,
                "submit_elicitation_decision",
                AsyncMock(return_value={"status": "answered"}),
            ) as submit:
                response = await main.handle_elicit(
                    self.request(
                        {
                            "session_id": session_id,
                            "elicitation_id": "question",
                            "action": "accept",
                        },
                        session_id=session_id,
                    )
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(submit.await_args.args[0], session_id)

    async def test_elicitation_rejects_other_or_invalid_caller_sessions(self):
        with patch.object(main, "submit_elicitation_decision", AsyncMock()) as submit:
            for action in ("accept", "decline", "cancel"):
                with self.subTest(action=action):
                    response = await main.handle_elicit(
                        self.request(
                            {
                                "session_id": "other-session",
                                "elicitation_id": "question",
                                "action": action,
                            },
                            session_id="caller-session",
                        )
                    )
                    self.assertEqual(response.status_code, 403)
            for caller in (None, 123, "", "../escape"):
                with self.subTest(caller=caller):
                    response = await main.handle_elicit(
                        self.request(
                            {
                                "session_id": "session",
                                "elicitation_id": "question",
                                "action": "accept",
                            },
                            session_id=caller,
                        )
                    )
                    self.assertEqual(response.status_code, 400)
            submit.assert_not_awaited()

    async def test_elicit_custom_route_resolves_session_without_body_fallback(self):
        import httpx

        body = {
            "session_id": "session",
            "elicitation_id": "question",
            "action": "accept",
        }
        with patch.object(main.app.config, "session_id", ""), patch.object(
            main,
            "submit_elicitation_decision",
            AsyncMock(return_value={"status": "answered"}),
        ) as submit:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://localhost",
            ) as client:
                missing = await client.post("/elicit", json=body)
                self.assertEqual(missing.status_code, 400)
                mismatch = await client.post(
                    "/elicit?agent_session_id=other-session", json=body
                )
                self.assertEqual(mismatch.status_code, 403)
                matching = await client.post(
                    "/elicit?agent_session_id=session", json=body
                )
                self.assertEqual(matching.status_code, 200)
                submit.assert_awaited_once_with("session", "question", "accept", None)
                submit.reset_mock()
                with patch.object(main.app.config, "session_id", "hosted-session"):
                    override = await client.post(
                        "/elicit?agent_session_id=session", json=body
                    )
                    self.assertEqual(override.status_code, 403)
                    submit.assert_not_awaited()
                    matching_hosted = await client.post(
                        "/elicit?agent_session_id=session",
                        json={**body, "session_id": "hosted-session"},
                    )
                    self.assertEqual(matching_hosted.status_code, 200)
                    submit.assert_awaited_once_with(
                        "hosted-session", "question", "accept", None
                    )

    async def test_non_string_elicitation_ids_are_rejected(self):
        with patch.object(main, "submit_elicitation_decision", AsyncMock()) as submit:
            for value in (None, 0, False):
                with self.subTest(value=value):
                    response = await main.handle_elicit(
                        self.request(
                            {
                                "session_id": "session",
                                "elicitation_id": value,
                                "action": "accept",
                            },
                            session_id="session",
                        )
                    )
                    self.assertEqual(response.status_code, 400)
            submit.assert_not_awaited()

    async def test_no_live_harness_falls_back_to_framework_durable_turn(self):
        request = self.request(
            {"input": "hello", "mode": "immediate", "input_id": "stable"},
            session_id="session",
        )
        stream = SimpleNamespace()
        with patch.object(
            main, "submit_native_input", AsyncMock(return_value=None)
        ), patch.object(
            main.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            main.copilot_agent, "start", AsyncMock()
        ) as start, patch.object(
            main, "reserve_harness"
        ):
            response = await main.handle_invoke(request)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(response.body)["action"], "start")
        start.assert_awaited_once()

    async def test_concurrent_first_requests_reserve_before_stream_await(self):
        stream_entered = asyncio.Event()
        stream_release = asyncio.Event()
        harness = SimpleNamespace(
            queue_input=AsyncMock(
                return_value={
                    "status": "delivered",
                    "input_id": "same-id",
                    "deduplicated": True,
                }
            )
        )

        async def get_stream(_invocation_id):
            stream_entered.set()
            await stream_release.wait()
            return SimpleNamespace()

        async def start_task(**_kwargs):
            slot = agent._HARNESS_SLOTS["session"]
            if not slot.ready.done():
                slot.ready.set_result(harness)

        with patch.object(
            main.streams, "get_or_create", side_effect=get_stream
        ) as get_or_create, patch.object(
            main.copilot_agent, "start", side_effect=start_task
        ) as start:
            first = asyncio.create_task(
                main.handle_invoke(
                    self.request(
                        {"input": "hello", "input_id": "same-id"},
                        session_id="session",
                        invocation_id="first",
                    )
                )
            )
            await stream_entered.wait()
            second = asyncio.create_task(
                main.handle_invoke(
                    self.request(
                        {"input": "hello", "input_id": "same-id"},
                        session_id="session",
                        invocation_id="second",
                    )
                )
            )
            await asyncio.sleep(0)
            start.assert_not_awaited()
            stream_release.set()
            first_response, second_response = await asyncio.gather(first, second)

        self.assertEqual(json.loads(first_response.body)["action"], "start")
        self.assertEqual(json.loads(second_response.body)["action"], "queue")
        start.assert_awaited_once()
        get_or_create.assert_awaited_once_with("first")
        harness.queue_input.assert_awaited_once_with("same-id", "hello", "enqueue")

    async def test_stream_start_failure_wakes_followers_and_allows_fresh_reservation(
        self,
    ):
        stream_entered = asyncio.Event()
        stream_release = asyncio.Event()
        calls = 0
        replacement_harness = SimpleNamespace(queue_input=AsyncMock())

        async def get_stream(_invocation_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                stream_entered.set()
                await stream_release.wait()
                raise OSError("stream creation failed")
            return SimpleNamespace()

        async def start_task(**_kwargs):
            slot = agent._HARNESS_SLOTS["session"]
            if not slot.ready.done():
                slot.ready.set_result(replacement_harness)

        with patch.object(
            main.streams, "get_or_create", side_effect=get_stream
        ), patch.object(main.copilot_agent, "start", side_effect=start_task) as start:
            first = asyncio.create_task(
                main.handle_invoke(
                    self.request(
                        {"input": "first", "input_id": "first-id"},
                        session_id="session",
                        invocation_id="first",
                    )
                )
            )
            await stream_entered.wait()
            follower = asyncio.create_task(
                main.handle_invoke(
                    self.request(
                        {"input": "follow", "input_id": "follow-id"},
                        session_id="session",
                        invocation_id="follower",
                    )
                )
            )
            stream_release.set()
            outcomes = await asyncio.wait_for(
                asyncio.gather(first, follower, return_exceptions=True),
                2,
            )
            self.assertTrue(
                all(
                    isinstance(outcome, OSError)
                    and str(outcome) == "stream creation failed"
                    for outcome in outcomes
                )
            )
            self.assertNotIn("session", agent._HARNESS_SLOTS)

            retry = await main.handle_invoke(
                self.request(
                    {"input": "retry", "input_id": "retry-id"},
                    session_id="session",
                    invocation_id="retry",
                )
            )

        self.assertEqual(retry.status_code, 202)
        self.assertEqual(json.loads(retry.body)["action"], "start")
        start.assert_awaited_once()

    async def test_polling_old_invocation_stays_terminal_during_new_turn(self):
        statuses = {
            "old": {
                "task_id": "copilot-session",
                "invocation_id": "old",
                "status": "completed",
                "task_status": "suspended",
                "payload": None,
            },
            "new": {
                "task_id": "copilot-session",
                "invocation_id": "new",
                "status": "running",
                "task_status": "in_progress",
                "payload": None,
            },
        }

        async def get_status(invocation_id):
            return copy.deepcopy(statuses.get(invocation_id))

        with patch.object(main, "get_invocation_status", side_effect=get_status):
            old_response = await main.handle_get(
                self.request(
                    method="GET",
                    invocation_id="old",
                )
            )
            new_response = await main.handle_get(
                self.request(
                    method="GET",
                    invocation_id="new",
                )
            )
            statuses["new"]["status"] = "completed"
            statuses["new"]["task_status"] = "suspended"
            old_after = await main.handle_get(
                self.request(method="GET", invocation_id="old")
            )
            missing = await main.handle_get(
                self.request(method="GET", invocation_id="unknown")
            )

        self.assertEqual(json.loads(old_response.body)["status"], "completed")
        self.assertEqual(json.loads(new_response.body)["status"], "running")
        self.assertEqual(json.loads(old_after.body)["status"], "completed")
        self.assertEqual(json.loads(old_after.body)["invocation_id"], "old")
        self.assertEqual(
            set(json.loads(old_after.body)),
            {"task_id", "invocation_id", "status", "task_status", "payload"},
        )
        self.assertEqual(missing.status_code, 404)

    async def test_cancel_race_cannot_cancel_replacement_input(self):
        invocation_a = {
            "task_id": "copilot-session",
            "framework_input_id": "framework-a",
            "status": "running",
        }
        run_b = SimpleNamespace(cancel=AsyncMock())

        async def exact_lookup(task_id, framework_input_id):
            self.assertEqual(task_id, "copilot-session")
            # A completed and B became active after the metadata read.
            return run_b if framework_input_id == "framework-b" else None

        with patch.object(
            main, "get_invocation_status", AsyncMock(return_value=invocation_a)
        ), patch.object(
            main.copilot_agent,
            "get_active_run",
            AsyncMock(side_effect=exact_lookup),
        ) as get_active:
            response = await main.handle_cancel(
                self.request(
                    method="POST",
                    invocation_id="invocation-a",
                    session_id="session",
                )
            )

        self.assertEqual(json.loads(response.body)["status"], "not_found")
        get_active.assert_awaited_once_with("copilot-session", "framework-a")
        run_b.cancel.assert_not_awaited()

    async def test_cancel_rejects_mismatched_session_and_legacy_identity(self):
        get_active = AsyncMock()
        with patch.object(
            main,
            "get_invocation_status",
            AsyncMock(
                return_value={
                    "task_id": "copilot-other",
                    "framework_input_id": "framework-a",
                    "status": "running",
                }
            ),
        ), patch.object(main.copilot_agent, "get_active_run", get_active):
            mismatched = await main.handle_cancel(
                self.request(
                    method="POST",
                    invocation_id="invocation-a",
                    session_id="session",
                )
            )
        self.assertIn("does not belong", json.loads(mismatched.body)["message"])
        get_active.assert_not_awaited()

        with patch.object(
            main,
            "get_invocation_status",
            AsyncMock(
                return_value={
                    "task_id": "copilot-session",
                    "status": "running",
                }
            ),
        ), patch.object(main.copilot_agent, "get_active_run", get_active):
            legacy = await main.handle_cancel(
                self.request(
                    method="POST",
                    invocation_id="legacy",
                    session_id="session",
                )
            )
        self.assertIn("no exact framework input", json.loads(legacy.body)["message"])
        get_active.assert_not_awaited()

    async def test_cancel_exact_framework_input_cancels_matching_run(self):
        run = SimpleNamespace(cancel=AsyncMock())
        with patch.object(
            main,
            "get_invocation_status",
            AsyncMock(
                return_value={
                    "task_id": "copilot-session",
                    "framework_input_id": "framework-b",
                    "status": "running",
                }
            ),
        ), patch.object(
            main.copilot_agent,
            "get_active_run",
            AsyncMock(return_value=run),
        ) as get_active:
            response = await main.handle_cancel(
                self.request(
                    method="POST",
                    invocation_id="invocation-b",
                    session_id="session",
                )
            )
        self.assertEqual(json.loads(response.body)["status"], "cancelled")
        get_active.assert_awaited_once_with("copilot-session", "framework-b")
        run.cancel.assert_awaited_once()

    async def test_sse_done_frame_uses_requested_invocation_id(self):
        class Stream:
            async def subscribe(self, after=None):
                if False:
                    yield None

        with patch.object(main.streams, "get", AsyncMock(return_value=Stream())):
            response = await main.handle_get(
                self.request(
                    method="GET",
                    invocation_id="old",
                    accept="text/event-stream",
                )
            )
            body = b"".join([chunk async for chunk in response.body_iterator])
        self.assertIn(b'"invocation_id": "old"', body)


if __name__ == "__main__":
    unittest.main()
