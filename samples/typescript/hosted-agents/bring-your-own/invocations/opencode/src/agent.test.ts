import assert from "node:assert/strict";
import test from "node:test";
import { createFoundryFetch } from "./agent.js";

test("authenticates only the configured Responses endpoint and preserves tool items", async () => {
  const endpoint = "https://example.services.ai.azure.com/api/projects/test";
  const url = `${endpoint}/openai/v1/responses`;
  const signal = new AbortController().signal;
  let tokenCalls = 0;
  let requests = 0;
  const fetcher: typeof fetch = async (input, init) => {
    requests++;
    assert.equal(String(input), url);
    assert.equal(init?.redirect, "error");
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("authorization"), `Bearer token-${requests}`);
    assert.equal(headers.get("api-key"), null);
    assert.deepEqual(JSON.parse(String(init?.body)).input, [
      { role: "user", content: "Hello", type: "message" },
      { role: "assistant", content: "Hi", type: "message" },
      { type: "function_call_output", call_id: "call_1", output: "done" },
    ]);
    return Response.json({ ok: true });
  };
  const modelFetch = createFoundryFetch(endpoint, signal, {
    async getToken(scope, options) {
      assert.equal(scope, "https://ai.azure.com/.default");
      assert.equal(options.abortSignal, signal);
      tokenCalls++;
      return { token: `token-${tokenCalls}` };
    },
  }, fetcher);
  const request = {
    method: "POST",
    headers: { "content-type": "application/json", "api-key": "placeholder" },
    body: JSON.stringify({
      input: [
        { role: "user", content: "Hello" },
        { role: "assistant", content: "Hi", type: "" },
        { type: "function_call_output", call_id: "call_1", output: "done" },
      ],
    }),
  };
  await modelFetch(url, request);
  await modelFetch(url, request);
  await assert.rejects(modelFetch("https://example.org/responses", request), /outside the configured/);
  assert.equal(tokenCalls, 2);
  assert.equal(requests, 2);
});
