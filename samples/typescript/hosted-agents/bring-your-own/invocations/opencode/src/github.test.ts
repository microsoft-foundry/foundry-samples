import assert from "node:assert/strict";
import test from "node:test";
import { GitHub } from "./github.js";

test("creates a draft PR against the configured repository without putting the token in the URL", async () => {
  let called = false;
  const fetcher: typeof fetch = async (input, init) => {
    called = true;
    assert.equal(String(input), "https://api.github.com/repos/example/billing/pulls");
    assert.equal(init?.redirect, "error");
    assert.equal(new Headers(init?.headers).get("authorization"), "Bearer secret-token");
    const body = JSON.parse(String(init?.body));
    assert.equal(body.draft, true);
    assert.equal(body.head, "fha/opencode-issue-7");
    assert.equal(body.base, "main");
    assert.match(body.body, /AI assistant on behalf of the PR author/);
    return Response.json({ number: 42, state: "open", draft: true, head: { sha: "a".repeat(40) } }, { status: 201 });
  };
  const github = new GitHub({ owner: "example", name: "billing" }, "secret-token", fetcher);
  const result = await github.createDraftPullRequest(
    { number: 7, title: "Fix suspended seats", body: "" },
    "main",
    new AbortController().signal,
  );
  assert.ok(called);
  assert.equal(result.url, "https://github.com/example/billing/pull/42");
  assert.equal(result.draft, true);
});

test("returns no branch on 404 and surfaces other GitHub failures without response secrets", async () => {
  const missing = new GitHub({ owner: "example", name: "billing" }, "secret-token", async () => (
    new Response("", { status: 404 })
  ));
  assert.equal(await missing.getBranchCommit(7, new AbortController().signal), undefined);

  const denied = new GitHub({ owner: "example", name: "billing" }, "secret-token", async () => (
    new Response("secret-token", { status: 403 })
  ));
  await assert.rejects(denied.getRepository(new AbortController().signal), (error: Error) => {
    assert.match(error.message, /HTTP 403/);
    assert.doesNotMatch(error.message, /secret-token/);
    return true;
  });
});
