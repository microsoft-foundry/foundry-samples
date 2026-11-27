import assert from "node:assert/strict";
import { request } from "node:http";
import type { AddressInfo } from "node:net";
import test from "node:test";
import { loadSettings, type Settings } from "./config.js";
import { createApp } from "./server.js";
import type { runWorker } from "./worker.js";

const settings: Settings = {
  projectEndpoint: "https://example.services.ai.azure.com/api/projects/test",
  model: "test-model",
  repository: { owner: "example", name: "billing" },
  githubToken: "test-token",
  port: 8088,
};

async function listen(t: test.TestContext, worker: typeof runWorker) {
  const app = createApp(settings, worker);
  await new Promise<void>((resolve) => app.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise<void>((resolve, reject) => {
    app.close((error) => error ? reject(error) : resolve());
    app.closeAllConnections();
  }));
  return `http://127.0.0.1:${(app.address() as AddressInfo).port}`;
}

test("validates the request and streams a bounded one-at-a-time invocation", async (t) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let started!: () => void;
  const running = new Promise<void>((resolve) => { started = resolve; });
  const url = await listen(t, async (_settings, number, _signal, progress) => {
    assert.equal(number, 7);
    progress("Testing.");
    started();
    await gate;
    return { status: "no_changes" };
  });
  assert.equal((await fetch(`${url}/readiness`)).status, 200);
  assert.equal((await fetch(`${url}/invocations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: '{"issue":0}',
  })).status, 400);
  assert.equal((await fetch(`${url}/invocations`, {
    method: "POST",
    body: "x".repeat(17_000),
  })).status, 413);

  const first = await fetch(`${url}/invocations?agent_session_id=example-session`, {
    method: "POST",
    headers: { "content-type": "text/plain" },
    body: "Fix issue #7",
  });
  await running;
  const busy = await fetch(`${url}/invocations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: '{"input":"Fix issue #7"}',
  });
  assert.equal(busy.status, 429);
  release();
  const events = await first.text();
  assert.match(first.headers.get("content-type") ?? "", /text\/event-stream/);
  assert.match(events, /event: started/);
  assert.match(events, /event: progress/);
  assert.match(events, /event: complete\ndata: {"status":"no_changes"}/);
});

test("rejects a malformed request URL without interrupting an active invocation", { timeout: 10_000 }, async (t) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  t.after(() => release());
  let started!: () => void;
  const running = new Promise<void>((resolve) => { started = resolve; });
  const url = await listen(t, async () => {
    started();
    await gate;
    return { status: "no_changes" };
  });
  const invocation = await fetch(`${url}/invocations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: '{"issue":7}',
  });
  await running;

  const endpoint = new URL(url);
  const malformed = await new Promise<{ status: number | undefined; body: string }>((resolve, reject) => {
    const req = request({
      hostname: endpoint.hostname,
      port: endpoint.port,
      path: "//[",
      signal: AbortSignal.timeout(5_000),
    }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk: string) => { body += chunk; });
      response.on("end", () => resolve({ status: response.statusCode, body }));
      response.on("error", reject);
    });
    req.on("error", reject);
    req.end();
  });
  assert.equal(malformed.status, 400);
  assert.match(malformed.body, /Invalid request URL/);
  assert.equal((await fetch(`${url}/readiness`)).status, 200);
  release();
  assert.match(await invocation.text(), /event: complete\ndata: {"status":"no_changes"}/);
});

test("emits an error event instead of a completion event on worker failure", async (t) => {
  const url = await listen(t, async () => { throw new Error("test-token failed"); });
  const response = await fetch(`${url}/invocations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: '{"issue":7}',
  });
  const events = await response.text();
  assert.match(events, /event: error/);
  assert.match(events, /\[redacted\] failed/);
  assert.doesNotMatch(events, /event: complete/);
});

test("validates the configured project and repository before listening", () => {
  const env = {
    AZURE_AI_PROJECT_ENDPOINT: "https://example.services.ai.azure.com/api/projects/test/",
    AZURE_AI_MODEL_DEPLOYMENT_NAME: "gpt-6-sol",
    GITHUB_REPOSITORY: "example/billing",
    GITHUB_TOKEN: "test-token",
  };
  assert.equal(loadSettings(env).projectEndpoint, "https://example.services.ai.azure.com/api/projects/test");
  assert.throws(() => loadSettings({ ...env, GITHUB_REPOSITORY: "../billing" }), /owner\/repository/);
  assert.throws(() => loadSettings({ ...env, AZURE_AI_PROJECT_ENDPOINT: "http://example.test" }), /HTTPS/);
});

test("uses the project endpoint injected by Foundry for hosted sessions", () => {
  const env = {
    FOUNDRY_PROJECT_ENDPOINT: "https://hosted.services.ai.azure.com/api/projects/hosted/",
    AZURE_AI_MODEL_DEPLOYMENT_NAME: "gpt-6-sol",
    GITHUB_REPOSITORY: "example/billing",
    GITHUB_TOKEN: "test-token",
  };
  assert.equal(loadSettings(env).projectEndpoint, "https://hosted.services.ai.azure.com/api/projects/hosted");
  assert.equal(
    loadSettings({ ...env, AZURE_AI_PROJECT_ENDPOINT: "https://local.services.ai.azure.com/api/projects/local" })
      .projectEndpoint,
    "https://hosted.services.ai.azure.com/api/projects/hosted",
  );
});
