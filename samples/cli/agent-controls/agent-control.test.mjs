import assert from "node:assert/strict";
import { once } from "node:events";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { AgentContextBuilder, InterceptionPoint } from "@responsibleai/agent-hooks";
import {
  AgentControlClient,
  PolicyDenied,
  validateJson,
} from "./agent-control.mjs";

const ACCOUNT = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/sample/providers/Microsoft.CognitiveServices/accounts/sample";
const POLICY = `${ACCOUNT}/raiPolicies/refund-guard`;
const credential = { async getToken() { return { token: "synthetic-test-token" }; } };
const context = () => new AgentContextBuilder({
  agentId: "test-agent", framework: "custom", sessionId: "test-session",
}).preToolCall("test-call", "refund_order", { amount: 100 });

function evaluation(request, acsVerdict = { decision: "allow" }, content = request.content) {
  return {
    verdict: acsVerdict.decision === "deny" ? "blocked" : "allowed",
    acsVerdict,
    ...(acsVerdict.decision === "deny" ? {} : { content }),
  };
}

function client(fetch, extra = {}) {
  return new AgentControlClient({
    endpoint: "https://sample.cognitiveservices.azure.com/",
    policyId: POLICY,
    credential,
    fetch,
    ...extra,
  });
}

test("September sends the unchanged policy ID and encoded tool arguments in the body", async () => {
  let calls = 0;
  const instance = client(async (url, options) => {
    calls += 1;
    assert.equal(url.pathname, "/contentsafety/content:unifiedModerate");
    assert.equal(url.searchParams.get("api-version"), "2026-09-01-preview");
    assert.equal(url.searchParams.has("policyId"), false);
    assert.equal(options.method, "POST");
    assert.equal(options.redirect, "error");
    const sent = JSON.parse(options.body);
    assert.deepEqual(sent, {
      policyId: POLICY,
      source: "pre_tool_call",
      content: '{"amount":100}',
      toolName: "refund_order",
      toolCallId: "test-call",
      context: { agentId: "test-agent", sessionId: "test-session", sequence: 0 },
    });
    return Response.json(evaluation(sent));
  });
  let dispatched = 0;
  await instance.guard(context(), () => { dispatched += 1; });
  assert.equal(calls, 1);
  assert.equal(dispatched, 1);
});

test("HTTP 200 with deny never dispatches, including a deny with approval metadata", async () => {
  for (const verdict of [
    { decision: "deny", reason: "over_limit" },
    { decision: "deny", reason: "review", approval: { type: "human_review" } },
  ]) {
    const instance = client(async (_, options) =>
      Response.json(evaluation(JSON.parse(options.body), verdict)));
    let dispatched = 0;
    await assert.rejects(instance.guard(context(), () => { dispatched += 1; }), PolicyDenied);
    assert.equal(dispatched, 0);
  }
});

test("a transform changes the actual dispatched arguments without mutating the caller's context", async () => {
  const instance = client(async (_, options) => Response.json(evaluation(JSON.parse(options.body), {
    decision: "transform", transform: { path: "$target.amount", value: "50" },
  }, '{"amount":50}')));
  const original = context();
  const result = await instance.guard(original, (approved) => approved.tool_call.args.amount);
  assert.equal(result.value, 50);
  assert.equal(original.tool_call.args.amount, 100);
  assert.deepEqual(result.evaluation.context.target, { amount: 50 });
});

test("text and tool-result transforms use final content rather than reapplying metadata", async () => {
  const builder = new AgentContextBuilder({ agentId: "test", framework: "custom", sessionId: "transform" });
  for (const ctx of [
    builder.input("original"),
    builder.output("original"),
    builder.postToolCall("call", "refund_order", {}, ["original"]),
  ]) {
    const text = ctx.interception_point !== "post_tool_call";
    const instance = client(async (_, options) => Response.json(evaluation(JSON.parse(options.body), {
      decision: "transform",
      transform: { path: text ? "$target.content" : "$target[0]", value: '"replacement"' },
    }, text ? "replacement" : '["replacement"]')));
    const result = await instance.guard(ctx, (approved) => approved.target);
    assert.deepEqual(result.value, text ? { ...ctx.target, content: "replacement" } : ["replacement"]);
    assert.deepEqual(ctx.target, text ? { ...ctx.target, content: "original" } : ["original"]);
  }
});

test("all eight canonical lifecycle contexts are accepted", async () => {
  const builder = new AgentContextBuilder({ agentId: "test", framework: "custom", sessionId: "all-points" });
  const contexts = [
    builder.agentStartup(["refund_order"]),
    builder.input("hello"),
    builder.preModelCall("simulator", [{ role: "user", content: "hello" }]),
    builder.postModelCall("simulator", "hello", [], "stop"),
    builder.preToolCall("one", "refund_order", { amount: 100 }),
    builder.postToolCall("one", "refund_order", { amount: 100 }, { status: "simulated" }),
    builder.output("complete"),
    builder.agentShutdown("completed"),
  ];
  assert.deepEqual(contexts.map((value) => value.interception_point), Object.values(InterceptionPoint));
  const expectedContent = [
    { tools_registered: ["refund_order"] }, "hello",
    { messages: [{ role: "user", content: "hello" }] },
    { content: "hello", tool_calls: [], finish_reason: "stop" },
    { amount: 100 }, { status: "simulated" }, "complete", { reason: "completed" },
  ];
  let index = 0;
  const instance = client(async (_, options) => {
    const request = JSON.parse(options.body);
    const point = contexts[index].interception_point;
    assert.equal(request.source, point);
    assert.equal(typeof request.content, "string");
    assert.deepEqual(
      point === "input" || point === "output" ? request.content : JSON.parse(request.content),
      expectedContent[index],
    );
    assert.deepEqual(request.context, { agentId: "test", sessionId: "all-points", sequence: index });
    if (point === "pre_model_call" || point === "post_model_call") {
      assert.equal(request.modelId, "simulator");
    }
    if (point === "post_tool_call") {
      assert.equal(request.toolName, "refund_order");
      assert.equal(request.toolCallId, "one");
      assert.deepEqual(JSON.parse(request.toolArguments), { amount: 100 });
      assert.equal(request.toolResultIsError, false);
    }
    index += 1;
    return Response.json(evaluation(request));
  });
  for (const ctx of contexts) await instance.guard(ctx, () => undefined);
  assert.equal(index, 8);
});

test("post-tool JSON strings, false and zero retain their types and metadata", async () => {
  for (const value of ["123", false, 0]) {
    const builder = new AgentContextBuilder({ agentId: "test", framework: "custom", sessionId: "post-tool" });
    const ctx = builder.postToolCall("call", "refund_order", { amount: 100 }, value, true);
    ctx.tool_result.duration_ms = 0;
    const instance = client(async (_, options) => {
      const request = JSON.parse(options.body);
      assert.equal(JSON.parse(request.content), value);
      assert.equal(request.toolResultIsError, true);
      assert.equal(request.toolDurationMs, 0);
      return Response.json(evaluation(request));
    });
    assert.equal((await instance.guard(ctx, (approved) => approved.tool_result.value)).value, value);
  }
});

test("HTTP failures stop execution instead of becoming policy allows", async () => {
  for (const status of [400, 401, 403, 404, 409, 429, 500, 503]) {
    const instance = client(async () => Response.json(
      { error: { code: "test_failure" } }, { status },
    ));
    let dispatched = 0;
    await assert.rejects(
      instance.guard(context(), () => { dispatched += 1; }),
      new RegExp(`HTTP ${status}`),
    );
    assert.equal(dispatched, 0);
  }
});

test("invalid or inconsistent September responses stop execution", async () => {
  const changes = [
    (result) => { result.verdict = "unknown"; },
    (result) => { result.verdict = { decision: "allow" }; },
    (result) => { delete result.acsVerdict; },
    (result) => { result.acsVerdict.decision = "unknown"; },
    (result) => { result.acsVerdict.decision = "deny"; },
    (result) => { result.verdict = "blocked"; },
    (result) => { delete result.content; },
    (result) => { result.content = {}; },
    (result) => { result.content = "not-json"; },
    (result) => { result.content = '{"amount":101}'; },
    (result) => { result.acsVerdict = { decision: "transform" }; },
    (result) => { result.acsVerdict = { decision: "transform", transform: { path: "$target", value: {} } }; },
    (result) => { result.acsVerdict = { decision: "transform", transform: { path: "$other", value: "{}" } }; },
    (result) => { result.acsVerdict = { decision: "transform", transform: { path: "$target..bad", value: "{}" } }; },
    (result) => { result.acsVerdict = { decision: "transform", transform: { path: "$target", value: "not-json" } }; },
    (result) => {
      result.acsVerdict = { decision: "transform", transform: { path: "$target", value: "[]" } };
      result.content = "[]";
    },
  ];
  for (const change of changes) {
    const instance = client(async (_, options) => {
      const result = evaluation(JSON.parse(options.body));
      change(result);
      return Response.json(result);
    });
    let dispatched = 0;
    await assert.rejects(instance.guard(context(), () => { dispatched += 1; }));
    assert.equal(dispatched, 0);
  }
});

test("unrepresentable input roles and null tool results fail before sending", async () => {
  const builder = new AgentContextBuilder({ agentId: "test", framework: "custom", sessionId: "unsupported" });
  for (const ctx of [
    builder.input("hello", "system"),
    builder.postToolCall("call", "refund_order", {}, null),
  ]) {
    let requests = 0;
    const instance = client(async () => { requests += 1; throw new Error("must not send"); });
    await assert.rejects(instance.guard(ctx, () => { throw new Error("must not run"); }));
    assert.equal(requests, 0);
  }
});

test("context/target mismatches are rejected before the request is sent", async () => {
  const ctx = context();
  ctx.target = { amount: 99 };
  let requests = 0;
  const instance = client(async () => { requests += 1; throw new Error("must not send"); });
  await assert.rejects(instance.evaluate(ctx));
  assert.equal(requests, 0);
});

test("malformed, oversized, and invalid UTF-8 responses stop execution", async () => {
  for (const body of ["not-json", "x".repeat(1_048_577), new Uint8Array([0xc3, 0x28])]) {
    const instance = client(async () => new Response(body));
    let dispatched = 0;
    await assert.rejects(instance.guard(context(), () => { dispatched += 1; }));
    assert.equal(dispatched, 0);
  }
});

test("oversized requests are rejected locally", async () => {
  const ctx = new AgentContextBuilder({ agentId: "test", framework: "custom", sessionId: "large" })
    .input("x".repeat(1_048_577));
  let requests = 0;
  const instance = client(async () => { requests += 1; throw new Error("must not send"); });
  await assert.rejects(instance.evaluate(ctx), /request exceeds/);
  assert.equal(requests, 0);
});

test("invalid native JSON values are not silently serialized away", () => {
  for (const value of [undefined, NaN, Infinity, new Date(), { member: undefined }, "\ud800"]) {
    assert.throws(() => validateJson(value));
  }
  let nested = {};
  for (let index = 0; index < 64; index += 1) nested = { child: nested };
  assert.throws(() => validateJson(nested), /depth/);
});

test("network and credential errors never dispatch", async () => {
  for (const instance of [
    client(async () => { throw new Error("network unavailable"); }),
    client(async () => { throw new Error("must not send"); }, {
      credential: { async getToken() { throw new Error("credential unavailable"); } },
    }),
  ]) {
    let dispatched = 0;
    await assert.rejects(instance.guard(context(), () => { dispatched += 1; }));
    assert.equal(dispatched, 0);
  }
});

test("startup transforms are rejected", async () => {
  const ctx = new AgentContextBuilder({ agentId: "test", framework: "custom", sessionId: "startup" })
    .agentStartup(["refund_order"]);
  const instance = client(async (_, options) => Response.json(evaluation(JSON.parse(options.body), {
    decision: "transform", transform: { path: "$target", value: "{}" },
  })));
  await assert.rejects(instance.guard(ctx, () => { throw new Error("must not run"); }));
});

test("the operation deadline aborts an in-flight HTTP request", async () => {
  const server = createServer(() => undefined);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = server.address().port;
  let dispatched = 0;
  try {
    const instance = client(
      (_, options) => fetch(`http://127.0.0.1:${port}/`, options),
      { timeoutMs: 100 },
    );
    await assert.rejects(instance.guard(context(), () => { dispatched += 1; }), { name: "AbortError" });
    assert.equal(dispatched, 0);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("the unchanged host fixtures are adapted to September HTTP requests", async () => {
  for (const name of [
    "input", "output", "pre-tool", "pre-tool-denied",
    "approved-tool", "approved-url", "output-commitment",
  ]) {
    const ctx = JSON.parse(await readFile(new URL(`./requests/${name}.json`, import.meta.url), "utf8"));
    const instance = client(async (_, options) => Response.json(evaluation(JSON.parse(options.body))));
    await instance.evaluate(ctx);
  }
});
