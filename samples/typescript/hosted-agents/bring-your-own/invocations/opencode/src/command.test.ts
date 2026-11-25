import assert from "node:assert/strict";
import { createServer, type AddressInfo, type Socket } from "node:net";
import test from "node:test";
import { runCommand } from "./command.js";

test("preserves UTF-8 output across process-stream chunk boundaries", async () => {
  const script = [
    'const prefix = Buffer.alloc(65535, "a");',
    'const character = Buffer.from("💡");',
    "process.stdout.write(Buffer.concat([prefix, character.subarray(0, 1)]));",
    "setImmediate(() => process.stdout.write(character.subarray(1)));",
  ].join("\n");
  const output = await runCommand(process.execPath, ["-e", script], {
    cwd: process.cwd(),
    env: process.env,
    signal: new AbortController().signal,
  });
  assert.equal(output, `${"a".repeat(65535)}💡`);
});

test("cancellation kills a descendant even if it ignores SIGTERM and closes stdio", { timeout: 10_000 }, async (t) => {
  let connection: Socket | undefined;
  let childPid: number | undefined;
  let disconnected = false;
  let signalReady!: (value: { pid: number; closed: Promise<void> }) => void;
  const ready = new Promise<{ pid: number; closed: Promise<void> }>((resolve) => { signalReady = resolve; });
  const listener = createServer((socket) => {
    connection = socket;
    const closed = new Promise<void>((resolve) => socket.once("close", () => {
      disconnected = true;
      resolve();
    }));
    socket.once("data", (data) => {
      childPid = Number(data.toString());
      signalReady({ pid: childPid, closed });
    });
  });
  await new Promise<void>((resolve) => listener.listen(0, "127.0.0.1", resolve));
  t.after(() => {
    if (childPid && !disconnected) {
      try { process.kill(childPid, "SIGKILL"); } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
      }
    }
    connection?.destroy();
    listener.close();
  });
  const port = (listener.address() as AddressInfo).port;
  const child = [
    'const net = require("node:net");',
    `const socket = net.connect(${port}, "127.0.0.1");`,
    'process.on("SIGTERM", () => {});',
    'socket.once("connect", () => socket.write(String(process.pid)));',
    "setInterval(() => {}, 1000);",
  ].join("\n");
  const parent = [
    'const { spawn } = require("node:child_process");',
    `spawn(process.execPath, ["-e", ${JSON.stringify(child)}], { stdio: "ignore" });`,
    'process.on("SIGTERM", () => process.exit(0));',
    "setInterval(() => {}, 1000);",
  ].join("\n");
  const controller = new AbortController();
  const run = runCommand(process.execPath, ["-e", parent], {
    cwd: process.cwd(),
    env: process.env,
    signal: controller.signal,
  });
  const descendant = await ready;
  assert.ok(descendant.pid > 0);
  controller.abort(new Error("cancel process group"));
  await assert.rejects(run, /cancel process group/);
  await descendant.closed;
});
