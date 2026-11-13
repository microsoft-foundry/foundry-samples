import asyncio
import base64
from contextlib import closing
import importlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


SRC = Path(__file__).resolve().parents[1] / "src" / "resilient-copilot"
sys.path.insert(0, str(SRC))

from copilot.session import CopilotSession
import store as snapshot_module
from copilot_session import (
    CopilotHarness,
    TodoCheckpointDetectionFailure,
    TodoCheckpointRequest,
)
from store import (
    SessionSnapshotStore,
    SnapshotTooLargeError,
    _PIN_SCHEMA,
    _pack_dir,
    todo_fingerprint,
)


def create_todos(workspace: Path) -> sqlite3.Connection:
    workspace.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(workspace / "session.db")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE todos (id TEXT PRIMARY KEY, title TEXT, status TEXT)")
    db.execute("CREATE TABLE todo_deps (todo_id TEXT, depends_on TEXT)")
    db.commit()
    return db


def create_core_layout(root: Path, *, plan=True):
    config = root / "config"
    workspace = config / "session-state" / "test"
    checkpoints = workspace / "checkpoints"
    checkpoints.mkdir(parents=True)
    sqlite3.connect(config / "session-store.db").close()
    db = create_todos(workspace)
    db.execute("INSERT INTO todos VALUES ('a', 'step', 'done')")
    db.commit()
    db.close()
    (workspace / "events.jsonl").write_bytes(b'{"saved":true}\n{"partial":')
    (workspace / "workspace.yaml").write_text("workspace: test", encoding="utf-8")
    (checkpoints / "index.md").write_text("checkpoint", encoding="utf-8")
    if plan:
        (workspace / "plan.md").write_text("required plan", encoding="utf-8")
    return config, workspace


class TodoSnapshotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "config"
        self.workspace = self.config / "session-state" / "test"
        self.config.mkdir(parents=True)
        sqlite3.connect(self.config / "session-store.db").close()
        self.db = create_todos(self.workspace)
        self.addCleanup(self.db.close)
        self.store = SessionSnapshotStore(self.root / "snapshots")
        self.store._use_state_store = False

    def change_todo(self, status: str):
        self.db.execute(
            "INSERT INTO todos VALUES ('a', 'First step', ?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status",
            (status,),
        )
        self.db.commit()

    def test_fingerprint_tracks_todos_plan_registration_and_required_content(self):
        empty = todo_fingerprint(self.workspace)
        self.change_todo("pending")
        pending = todo_fingerprint(self.workspace)
        self.assertNotEqual(empty, pending)
        self.change_todo("done")
        done = todo_fingerprint(self.workspace)
        self.assertNotEqual(pending, done)
        self.db.execute("INSERT INTO todo_deps VALUES ('b', 'a')")
        self.db.commit()
        deps = todo_fingerprint(self.workspace)
        self.assertNotEqual(done, deps)
        (self.workspace / "plan.md").write_text("A then B", encoding="utf-8")
        plan = todo_fingerprint(self.workspace)
        self.assertNotEqual(deps, plan)
        (self.workspace / "required.txt").write_text("v1", encoding="utf-8")
        (self.workspace / "continuation-files.json").write_text(
            json.dumps({"schema": _PIN_SCHEMA, "paths": ["required.txt"]}),
            encoding="utf-8",
        )
        registered = todo_fingerprint(self.workspace)
        self.assertNotEqual(plan, registered)
        (self.workspace / "required.txt").write_text("v2", encoding="utf-8")
        self.assertNotEqual(registered, todo_fingerprint(self.workspace))
        (self.workspace / "required.txt").unlink()
        with self.assertRaises(FileNotFoundError):
            todo_fingerprint(self.workspace)

    async def test_live_snapshot_restores_committed_wal_todos_to_new_directory(self):
        self.change_todo("done")
        self.db.execute(
            "INSERT INTO todos VALUES ('uncommitted', 'Not saved', 'pending')"
        )
        (self.workspace / "plan.md").write_text("A then B", encoding="utf-8")
        (self.workspace / "inuse.lock").write_text("stale", encoding="utf-8")
        (self.workspace / "events.jsonl").write_bytes(b'{"type":"saved"}\n{"partial":')
        await self.store.save("test", self.config, live=True)

        restored = self.root / "replacement"
        self.assertTrue(await self.store.restore("test", restored))
        workspace = restored / "session-state" / "test"
        with closing(sqlite3.connect(workspace / "session.db")) as restored_db:
            self.assertEqual(
                restored_db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            self.assertEqual(
                restored_db.execute("SELECT id, status FROM todos").fetchall(),
                [("a", "done")],
            )
        self.assertEqual((workspace / "plan.md").read_text(), "A then B")
        self.assertEqual(
            (workspace / "events.jsonl").read_bytes(), b'{"type":"saved"}\n'
        )
        self.assertFalse((workspace / "inuse.lock").exists())

    async def test_latest_todo_checkpoint_replaces_previous_snapshot(self):
        for status in ("pending", "in_progress", "done"):
            self.change_todo(status)
            await self.store.save("test", self.config, live=True)
        self.assertTrue(await self.store.restore("test", self.root / "replacement"))
        with closing(
            sqlite3.connect(
                self.root / "replacement" / "session-state" / "test" / "session.db"
            )
        ) as restored_db:
            self.assertEqual(
                restored_db.execute("SELECT status FROM todos").fetchone()[0], "done"
            )

    async def test_write_failure_is_not_reported_as_saved(self):
        self.change_todo("pending")
        self.store._use_state_store = True
        self.store._store = SimpleNamespace(
            set_item=AsyncMock(side_effect=OSError("write failed"))
        )
        with self.assertRaisesRegex(OSError, "write failed"):
            await self.store.save("test", self.config, live=True)

    async def test_missing_session_directory_fails_explicitly(self):
        with self.assertRaises(FileNotFoundError):
            await self.store.save("test", self.root / "missing", live=True)

    async def test_hook_waits_for_checkpoint_and_skips_unchanged_todos(self):
        harness = CopilotHarness()
        harness._workspace = self.workspace
        harness._todo_fingerprint = todo_fingerprint(self.workspace)
        for status in ("pending", "in_progress", "done"):
            self.change_todo(status)
            hook = asyncio.create_task(harness._post_tool_use({}, {}))
            request = await asyncio.wait_for(harness._queue.get(), 2)
            self.assertIsInstance(request, TodoCheckpointRequest)
            self.assertFalse(hook.done())
            await self.store.save("test", self.config, live=True)
            request.acknowledged.set_result(None)
            await asyncio.wait_for(hook, 2)
            await harness._post_tool_use({}, {})
            self.assertTrue(harness._queue.empty())

    async def test_failed_checkpoint_does_not_advance_fingerprint(self):
        harness = CopilotHarness()
        harness._workspace = self.workspace
        original = todo_fingerprint(self.workspace)
        harness._todo_fingerprint = original
        self.change_todo("pending")
        hook = asyncio.create_task(harness._post_tool_use({}, {}))
        request = await asyncio.wait_for(harness._queue.get(), 2)
        request.acknowledged.set_exception(OSError("checkpoint failed"))
        with self.assertRaisesRegex(OSError, "checkpoint failed"):
            await hook
        self.assertEqual(harness._todo_fingerprint, original)

    async def test_pinned_sdk_swallow_still_delivers_detection_failure_to_consumer(
        self,
    ):
        harness = CopilotHarness()
        harness._workspace = self.workspace
        harness._todo_fingerprint = todo_fingerprint(self.workspace)
        sdk_session = CopilotSession("test", SimpleNamespace())
        sdk_session._hooks = {"on_post_tool_use": harness._post_tool_use}
        detection_error = sqlite3.DatabaseError("locked todo database")
        with patch("copilot_session.todo_fingerprint", side_effect=detection_error):
            dispatch = asyncio.create_task(
                sdk_session._handle_hooks_invoke("postToolUse", {})
            )
            failure = await asyncio.wait_for(harness._queue.get(), 2)
            self.assertIsInstance(failure, TodoCheckpointDetectionFailure)
            failure.acknowledged.set_exception(failure.error)
            self.assertIsNone(await asyncio.wait_for(dispatch, 2))

    async def test_close_unblocks_pending_hook(self):
        harness = CopilotHarness()
        harness._workspace = self.workspace
        harness._todo_fingerprint = todo_fingerprint(self.workspace)
        self.change_todo("pending")
        hook = asyncio.create_task(harness._post_tool_use({}, {}))
        await asyncio.wait_for(harness._queue.get(), 2)
        await harness.close()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(hook, 2)

    async def test_create_and_resume_register_checkpoint_hook(self):
        for recovered in (False, True):
            harness = CopilotHarness()
            session = SimpleNamespace(
                workspace_path=self.workspace, on=lambda cb: lambda: None
            )
            client = SimpleNamespace(
                start=AsyncMock(),
                create_session=AsyncMock(return_value=session),
                resume_session=AsyncMock(return_value=session),
                stop=AsyncMock(),
            )
            with patch(
                "copilot_session.CopilotClient", return_value=client
            ), patch.dict(
                os.environ, {"GITHUB_TOKEN": "unused-test-token"}
            ), patch.object(
                CopilotHarness, "_byok_provider", return_value=(None, None)
            ):
                await harness.start(
                    "test", recover=recovered, config_directory=str(self.config)
                )
            call = client.resume_session if recovered else client.create_session
            self.assertEqual(
                call.call_args.kwargs["hooks"]["on_post_tool_use"],
                harness._post_tool_use,
            )
            await harness.close()


class RequiredOnlySnapshotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    async def test_one_item_contains_core_and_pins_but_excludes_optional_files(self):
        config, workspace = create_core_layout(self.root)
        artifacts = workspace / "artifacts"
        artifacts.mkdir()
        (artifacts / "continuation.txt").write_text("required", encoding="utf-8")
        (workspace / "optional-output.txt").write_text("optional", encoding="utf-8")
        (workspace / "cache.db").write_bytes(b"optional database")
        (workspace / "uv.lock").write_text("uv lock", encoding="utf-8")
        (workspace / "continuation-files.json").write_text(
            json.dumps(
                {
                    "schema": _PIN_SCHEMA,
                    "paths": ["artifacts/continuation.txt", "uv.lock"],
                }
            ),
            encoding="utf-8",
        )
        store = SessionSnapshotStore(self.root / "snapshots")
        cloud = SimpleNamespace(set_item=AsyncMock(), get_item=AsyncMock())
        store._use_state_store = True
        store._store = cloud
        await store.save("test", config, live=True)
        key, value = cloud.set_item.call_args.args
        self.assertEqual(key, "test")
        with tarfile.open(
            fileobj=io.BytesIO(base64.b64decode(value["tar_gz_b64"])),
            mode="r:gz",
        ) as archive:
            names = set(archive.getnames())
        expected = {
            "session-store.db",
            "session-state/test/session.db",
            "session-state/test/events.jsonl",
            "session-state/test/workspace.yaml",
            "session-state/test/checkpoints/index.md",
            "session-state/test/plan.md",
            "session-state/test/continuation-files.json",
            "session-state/test/artifacts/continuation.txt",
            "session-state/test/uv.lock",
        }
        self.assertEqual(names, expected)
        cloud.get_item.return_value = SimpleNamespace(value=value)
        restored = self.root / "restored"
        self.assertTrue(await store.restore("test", restored))
        self.assertFalse(
            (restored / "session-state" / "test" / "optional-output.txt").exists()
        )
        self.assertFalse((restored / "session-state" / "test" / "cache.db").exists())

    async def test_explicit_lock_names_and_executable_mode_roundtrip(self):
        config, workspace = create_core_layout(self.root, plan=False)
        nested = workspace / "pins"
        nested.mkdir()
        (workspace / "uv.lock").write_text("uv lock", encoding="utf-8")
        executable = nested / "resume.lock"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        (workspace / "continuation-files.json").write_text(
            json.dumps(
                {
                    "schema": _PIN_SCHEMA,
                    "paths": ["uv.lock", "pins/resume.lock"],
                }
            ),
            encoding="utf-8",
        )
        store = SessionSnapshotStore(self.root / "snapshots")
        store._use_state_store = False
        await store.save("test", config, live=True)
        restored = self.root / "restored"
        self.assertTrue(await store.restore("test", restored))
        restored_workspace = restored / "session-state" / "test"
        self.assertEqual((restored_workspace / "uv.lock").read_text(), "uv lock")
        restored_executable = restored_workspace / "pins" / "resume.lock"
        self.assertEqual(restored_executable.read_text(), "#!/bin/sh\n")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(restored_executable.stat().st_mode), 0o755)

    async def test_pin_change_before_single_write_preserves_previous_snapshot(self):
        config, workspace = create_core_layout(self.root, plan=False)
        (workspace / "a.txt").write_text("a", encoding="utf-8")
        declaration = workspace / "continuation-files.json"
        declaration.write_text(
            json.dumps({"schema": _PIN_SCHEMA, "paths": ["a.txt"]}),
            encoding="utf-8",
        )
        store = SessionSnapshotStore(self.root / "snapshots")
        store._use_state_store = False
        await store.save("test", config, live=True)
        previous = store._path("test").read_bytes()
        (workspace / "b.txt").write_text("b", encoding="utf-8")
        original_pack = snapshot_module._pack_selected

        def mutate_declaration(*args, **kwargs):
            blob = original_pack(*args, **kwargs)
            declaration.write_text(
                json.dumps({"schema": _PIN_SCHEMA, "paths": ["b.txt"]}),
                encoding="utf-8",
            )
            return blob

        with patch.object(
            snapshot_module, "_pack_selected", side_effect=mutate_declaration
        ), self.assertRaisesRegex(RuntimeError, "changed while"):
            await store.save("test", config, live=True)
        self.assertEqual(store._path("test").read_bytes(), previous)

    async def test_pin_aba_during_pack_restores_frozen_declaration_and_selection(self):
        config, workspace = create_core_layout(self.root, plan=False)
        (workspace / "a.txt").write_text("a", encoding="utf-8")
        (workspace / "b.txt").write_text("b", encoding="utf-8")
        declaration = workspace / "continuation-files.json"
        declaration_a = json.dumps({"schema": _PIN_SCHEMA, "paths": ["a.txt"]}).encode()
        declaration.write_bytes(declaration_a)
        store = SessionSnapshotStore(self.root / "snapshots-aba")
        store._use_state_store = False
        original_pack = snapshot_module._pack_selected

        def aba_during_pack(*args, **kwargs):
            declaration.write_text(
                json.dumps({"schema": _PIN_SCHEMA, "paths": ["b.txt"]}),
                encoding="utf-8",
            )
            blob = original_pack(*args, **kwargs)
            declaration.write_bytes(declaration_a)
            return blob

        with patch.object(
            snapshot_module, "_pack_selected", side_effect=aba_during_pack
        ):
            await store.save("test", config, live=True)
        restored = self.root / "restored-aba"
        self.assertTrue(await store.restore("test", restored))
        restored_workspace = restored / "session-state" / "test"
        self.assertEqual(
            (restored_workspace / "continuation-files.json").read_bytes(),
            declaration_a,
        )
        self.assertTrue((restored_workspace / "a.txt").exists())
        self.assertFalse((restored_workspace / "b.txt").exists())

    async def test_pin_appearing_during_selection_is_archived_with_artifact(self):
        config, workspace = create_core_layout(self.root, plan=False)
        (workspace / "appeared.txt").write_text("appeared", encoding="utf-8")
        declaration = workspace / "continuation-files.json"
        original_load = snapshot_module._load_required_selection

        def create_then_load(selected_workspace):
            declaration.write_text(
                json.dumps(
                    {
                        "schema": _PIN_SCHEMA,
                        "paths": ["appeared.txt"],
                    }
                ),
                encoding="utf-8",
            )
            return original_load(selected_workspace)

        store = SessionSnapshotStore(self.root / "snapshots-appeared")
        store._use_state_store = False
        with patch.object(
            snapshot_module,
            "_load_required_selection",
            side_effect=create_then_load,
        ):
            await store.save("test", config, live=True)
        restored = self.root / "restored-appeared"
        self.assertTrue(await store.restore("test", restored))
        restored_workspace = restored / "session-state" / "test"
        self.assertTrue((restored_workspace / "continuation-files.json").exists())
        self.assertEqual((restored_workspace / "appeared.txt").read_text(), "appeared")

    async def test_invalid_or_missing_registered_files_fail(self):
        invalid = [
            {"schema": _PIN_SCHEMA, "paths": ["/absolute"]},
            {"schema": _PIN_SCHEMA, "paths": ["../escape"]},
            {"schema": _PIN_SCHEMA, "paths": ["missing.txt"]},
            {"schema": _PIN_SCHEMA, "paths": ["same.txt", "same.txt"]},
            {"schema": "wrong", "paths": []},
        ]
        for index, declaration in enumerate(invalid):
            with self.subTest(declaration=declaration):
                root = self.root / str(index)
                config, workspace = create_core_layout(root, plan=False)
                (workspace / "same.txt").write_text("same", encoding="utf-8")
                (workspace / "continuation-files.json").write_text(
                    json.dumps(declaration), encoding="utf-8"
                )
                store = SessionSnapshotStore(root / "snapshots")
                store._use_state_store = False
                with self.assertRaises((ValueError, FileNotFoundError)):
                    await store.save("test", config, live=True)

    async def test_broken_declaration_symlink_is_not_treated_as_absent(self):
        config, workspace = create_core_layout(self.root, plan=False)
        declaration = workspace / "continuation-files.json"
        store = SessionSnapshotStore(self.root / "snapshots-broken-declaration")
        store._use_state_store = False
        original_is_symlink = Path.is_symlink
        original_exists = Path.exists
        with patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=lambda path: (path == declaration or original_is_symlink(path)),
        ), patch.object(
            Path,
            "exists",
            autospec=True,
            side_effect=lambda path: (
                False if path == declaration else original_exists(path)
            ),
        ), patch.object(
            Path,
            "read_bytes",
            autospec=True,
            side_effect=AssertionError("broken declaration target must not be read"),
        ), self.assertRaisesRegex(
            ValueError, "must be a regular file"
        ):
            await store.save("test", config, live=True)
        self.assertFalse(store._path("test").exists())

    async def test_legacy_v2_and_v1_full_archives_still_restore(self):
        for version in ("v2", "v1"):
            with self.subTest(version=version):
                root = self.root / version
                source = root / "source"
                source.mkdir(parents=True)
                (source / "session-store.db").write_bytes(b"legacy")
                (source / "old-optional.txt").write_text("legacy", encoding="utf-8")
                store = SessionSnapshotStore(root / "snapshots")
                store._use_state_store = False
                path = (
                    store._path("test")
                    if version == "v2"
                    else store._legacy_path("test")
                )
                path.write_bytes(_pack_dir(source))
                restored = root / "restored"
                self.assertTrue(await store.restore("test", restored))
                self.assertTrue((restored / "old-optional.txt").exists())


class TaskCheckpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with patch.dict(os.environ, {"AGENTSERVER_STATE_ROOT": self.tmp.name}):
            self.agent = importlib.import_module("agent")

    async def exercise_task(
        self,
        *,
        checkpoint_failure=False,
        final_failure=False,
        detection_failure: BaseException | None = None,
    ):
        acknowledgement = asyncio.get_running_loop().create_future()
        request = (
            TodoCheckpointDetectionFailure(detection_failure, acknowledgement)
            if detection_failure is not None
            else TodoCheckpointRequest("todo-hash", acknowledgement)
        )

        class Harness:
            start = AsyncMock()
            send = AsyncMock()
            abort = AsyncMock()
            close = AsyncMock()
            stop_accepting_controls = lambda self: None
            bind_recovered_elicitations = lambda self, markers: None

            async def events(self):
                yield request
                await acknowledgement

        class Stream:
            def __init__(self):
                self.frames = []

            async def last_cursor(self):
                return 0

            async def emit(self, frame):
                self.frames.append(frame)

            close = AsyncMock()

        stream = Stream()
        state_store = SimpleNamespace(
            get_item=AsyncMock(return_value=None),
            set_item=AsyncMock(),
            aclose=AsyncMock(),
        )
        snapshot = SimpleNamespace(
            save=AsyncMock(), restore=AsyncMock(return_value=False)
        )
        invocation_store = SimpleNamespace(put=AsyncMock())
        expected_exception = None
        if detection_failure is not None:
            expected_exception = type(detection_failure)
        elif checkpoint_failure:
            failure = (
                checkpoint_failure
                if isinstance(checkpoint_failure, BaseException)
                else OSError("live snapshot failed")
            )
            snapshot.save.side_effect = failure
            expected_exception = type(failure)
        elif final_failure:
            snapshot.save.side_effect = [None, OSError("final snapshot failed")]
            expected_exception = OSError
        context = SimpleNamespace(
            input={"invocation_id": "test-inv", "prompt": "test", "session_id": "test"},
            input_id="framework-input",
            entry_mode="fresh",
            recovery_count=0,
            cancel=asyncio.Event(),
            shutdown=asyncio.Event(),
        )
        with patch.object(self.agent, "CopilotHarness", Harness), patch.object(
            self.agent, "_SNAPSHOT_STORE", snapshot
        ), patch.object(
            self.agent, "_INVOCATION_STORE", invocation_store
        ), patch.object(
            self.agent, "_CONFIG_ROOT", self.root / "task-config"
        ), patch.object(
            self.agent.streams, "get_or_create", AsyncMock(return_value=stream)
        ), patch.object(
            self.agent.FoundryStateStore,
            "get_or_create",
            AsyncMock(return_value=state_store),
        ), patch.object(
            self.agent, "_get_legacy_state_item", AsyncMock(return_value=None)
        ):
            handler = self.agent.copilot_agent._fn
            if expected_exception is not None:
                with self.assertRaises(expected_exception):
                    await handler(context)
            else:
                await handler(context)
        if acknowledgement.done() and not acknowledgement.cancelled():
            acknowledgement.exception()
        return snapshot, stream, state_store

    async def test_task_persists_live_checkpoint_then_completes_same_turn(self):
        snapshot, stream, state_store = await self.exercise_task()
        self.assertEqual(snapshot.save.await_count, 2)
        self.assertTrue(snapshot.save.call_args_list[0].kwargs["live"])
        self.assertEqual(
            [frame["type"] for frame in stream.frames],
            ["turn_start", "todo_checkpoint", "turn_complete"],
        )
        self.assertTrue(state_store.set_item.call_args.args[1]["has_snapshot"])

    async def test_failed_live_checkpoint_fails_turn_without_completion(self):
        _, stream, state_store = await self.exercise_task(checkpoint_failure=True)
        self.assertEqual(
            [frame["type"] for frame in stream.frames], ["turn_start", "turn_failed"]
        )
        for call in state_store.set_item.call_args_list:
            self.assertNotIn("has_snapshot", call.args[1])

    async def test_oversized_checkpoint_does_not_set_snapshot_marker(self):
        failure = SnapshotTooLargeError("5 MiB serialized JSON limit")
        _, stream, state_store = await self.exercise_task(checkpoint_failure=failure)
        self.assertEqual(
            [frame["type"] for frame in stream.frames], ["turn_start", "turn_failed"]
        )
        for call in state_store.set_item.call_args_list:
            self.assertNotIn("has_snapshot", call.args[1])

    async def test_detection_failure_emits_turn_failed_and_fails_task(self):
        failure = sqlite3.DatabaseError("locked todo database")
        snapshot, stream, state_store = await self.exercise_task(
            detection_failure=failure
        )
        snapshot.save.assert_not_awaited()
        self.assertEqual(
            [frame["type"] for frame in stream.frames],
            ["turn_start", "turn_failed"],
        )
        for call in state_store.set_item.call_args_list:
            self.assertNotIn("has_snapshot", call.args[1])

    async def test_failed_final_snapshot_does_not_emit_turn_complete(self):
        _, stream, _ = await self.exercise_task(final_failure=True)
        self.assertEqual(
            [frame["type"] for frame in stream.frames],
            ["turn_start", "todo_checkpoint", "turn_failed"],
        )


if __name__ == "__main__":
    unittest.main()
