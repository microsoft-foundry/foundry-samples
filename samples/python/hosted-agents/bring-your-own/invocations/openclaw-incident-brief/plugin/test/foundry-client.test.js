import assert from "node:assert/strict";
import test from "node:test";
import { FoundryClient } from "../foundry-client.js";
import plugin from "../index.js";

const config = {
  projectEndpoint: "https://example.services.ai.azure.com/api/projects/example",
  agentName: "incident-brief",
  sessionId: "session-1",
};
const credential = {
  async getToken(scope) {
    assert.equal(scope, "https://ai.azure.com/.default");
    return { token: "test-token" };
  },
};

test("start and status send the configured session and preserve the invocation ID", async () => {
  const calls = [];
  const client = new FoundryClient(config, {
    credential,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return Response.json({
        status: calls.length === 1 ? "pending" : "completed",
        invocation_id: "platform-invocation",
        job_id: "brief-123",
        session_id: config.sessionId,
        ...(calls.length === 2 ? { brief: "Impact: checkout errors." } : {}),
      });
    },
  });
  const started = await client.start("INC-42-v1", "Checkout errors.");
  const result = await client.status(started.invocation_id);
  assert.equal(result.brief, "Impact: checkout errors.");
  assert.equal(calls[0].url.pathname, "/api/projects/example/agents/incident-brief/endpoint/protocols/invocations");
  assert.equal(calls[0].url.searchParams.get("agent_session_id"), "session-1");
  assert.equal(calls[0].options.headers.authorization, "Bearer test-token");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    request_id: "INC-42-v1",
    updates: "Checkout errors.",
  });
  assert.equal(calls[1].url.pathname, `${calls[0].url.pathname}/platform-invocation`);
  assert.equal(calls[1].options.method, "GET");
  assert.equal(calls[1].url.searchParams.get("agent_session_id"), "session-1");
});

test("a conflicting request ID fails rather than looking successful", async () => {
  const client = new FoundryClient(config, {
    credential,
    fetchImpl: async () => Response.json({ error: "different updates" }, { status: 409 }),
  });
  await assert.rejects(client.start("same", "changed"), /HTTP 409.*different updates/);
});

test("malformed or mismatched status responses are rejected", async () => {
  const client = new FoundryClient(config, {
    credential,
    fetchImpl: async () =>
      Response.json({
        status: "completed",
        invocation_id: "other-invocation",
        job_id: "brief-123",
        session_id: config.sessionId,
      }),
  });
  await assert.rejects(client.status("expected-invocation"), /invalid incident-brief response/);
});

test("an aborted OpenClaw call is propagated to Azure authentication", async () => {
  const controller = new AbortController();
  const client = new FoundryClient(config, {
    credential: {
      async getToken(_scope, { abortSignal }) {
        assert.equal(abortSignal.aborted, true);
        throw abortSignal.reason;
      },
    },
  });
  controller.abort();
  await assert.rejects(client.start("id", "update", controller.signal), { name: "AbortError" });
});

test("the plugin registers both optional tools", () => {
  const names = [];
  plugin.register({
    registerTool(tool, options) {
      names.push(tool.name);
      assert.equal(options.optional, true);
    },
  });
  assert.deepEqual(names, ["foundry_incident_brief_start", "foundry_incident_brief_status"]);
});
