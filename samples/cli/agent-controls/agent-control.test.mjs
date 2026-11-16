import assert from "node:assert/strict";
import { once } from "node:events";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { AgentContextBuilder, InterceptionPoint } from "@responsibleai/agent-hooks";
import {
  AgentControlClient,
  API_VERSION,
  PolicyDenied,
  requestDigest,
  validateJson,
} from "./agent-control.mjs";

const ACCOUNT = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/sample/providers/Microsoft.CognitiveServices/accounts/sample";
const POLICY = `${ACCOUNT}/raiPolicies/refund-guard`;
const credential = { async getToken() { return { token: "synthetic-test-token" }; } };
const context = () => new AgentContextBuilder({
  agentId: "test-agent", framework: "custom", sessionId: "test-session",
}).preToolCall("test-call", "refund_order", { amount: 100 });

function evaluation(ctx, verdict = { decision: "allow" }) {
  return {
    verdict,
    receipt: {
      receiptVersion: API_VERSION,
      profile: "namedPolicy",
      evaluationId: "test-evaluation",
      attempt: 1,
      requestBinding: {
        algorithm: "sha256", canonicalization: "rfc8785", digest: requestDigest(ctx, POLICY),
      },
      evaluatedPolicyLayers: [{
        kind: "namedPolicy", policyResourceId: POLICY, policyRevision: '"test-revision"',
        policySemanticDigest: `sha256:${"1".repeat(64)}`,
        manifestRegoDigest: `sha256:${"2".repeat(64)}`,
        decision: verdict.decision,
      }],
      evaluatedInterventionPoint: ctx.interception_point,
      requiredInterventionPoints: [ctx.interception_point],
      hostProfileVersion: "test-profile",
      authenticatedProducerResourceId: ACCOUNT,
    },
  };
}

function client(fetch, extra = {}) {
  return new AgentControlClient({
    endpoint: "https://sample.cognitiveservices.azure.com/",
    policyId: POLICY,
    producerResourceId: ACCOUNT,
    credential,
    fetch,
    ...extra,
  });
}

test("the named-policy selector is encoded in the query, not the body", async () => {
  let calls = 0;
  const instance = client(async (url, options) => {
    calls += 1;
    assert.equal(url.pathname, "/contentsafety/content:unifiedModerate");
    assert.equal(url.searchParams.get("api-version"), API_VERSION);
    assert.equal(url.searchParams.get("policyId"), POLICY);
    assert.equal(options.method, "POST");
    assert.equal(options.redirect, "error");
    const sent = JSON.parse(options.body);
    assert.equal(typeof sent.tool_call.args.amount, "number");
    assert.equal(sent.policyId, undefined);
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
    decision: "transform", transform: { path: "$target.amount", value: 50 },
  })));
  const original = context();
  const result = await instance.guard(original, (approved) => approved.tool_call.args.amount);
  assert.equal(result.value, 50);
  assert.equal(original.tool_call.args.amount, 100);
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
  const instance = client(async (_, options) => Response.json(evaluation(JSON.parse(options.body))));
  for (const ctx of contexts) await instance.guard(ctx, () => undefined);
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

test("invalid verdicts and mismatched receipts stop execution", async () => {
  const changes = [
    (result) => { result.verdict = { decision: "unknown" }; },
    (result) => { result.verdict = {}; },
    (result) => { delete result.receipt; },
    (result) => { result.receipt.profile = "wrong-profile"; },
    (result) => { result.receipt.receiptVersion = "wrong-version"; },
    (result) => { result.receipt.requestBinding.digest = `sha256:${"0".repeat(64)}`; },
    (result) => { result.receipt.evaluatedInterventionPoint = "input"; },
    (result) => { result.receipt.requiredInterventionPoints = ["unsupported"]; },
    (result) => { result.receipt.authenticatedProducerResourceId = `${ACCOUNT}-other`; },
    (result) => { result.receipt.evaluatedPolicyLayers[0].policyResourceId = `${POLICY}-other`; },
    (result) => { result.receipt.evaluatedPolicyLayers[0].manifestRegoDigest = "invalid"; },
    (result) => {
      const layer = result.receipt.evaluatedPolicyLayers[0];
      layer.activatedArtifactDigest = layer.manifestRegoDigest;
      delete layer.manifestRegoDigest;
    },
    (result) => { result.receipt.evaluatedPolicyLayers[0].decision = "deny"; },
    (result) => { result.receipt.evaluatedPolicyLayers.push(structuredClone(result.receipt.evaluatedPolicyLayers[0])); },
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
    decision: "transform", transform: { path: "$target", value: {} },
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

test("the shipped HTTP request examples are canonical contexts", async () => {
  for (const name of [
    "input", "output", "pre-tool", "pre-tool-denied",
    "approved-tool", "approved-url", "output-commitment",
  ]) {
    const ctx = JSON.parse(await readFile(new URL(`./requests/${name}.json`, import.meta.url), "utf8"));
    const instance = client(async (_, options) => Response.json(evaluation(JSON.parse(options.body))));
    await instance.evaluate(ctx);
  }
});
