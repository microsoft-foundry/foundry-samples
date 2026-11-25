import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { commitMarker, issueBranch, type Settings } from "./config.js";
import type { GitHubApi, Issue, PullRequest } from "./github.js";
import { runWorker } from "./worker.js";

const exec = promisify(execFile);
const demo = fileURLToPath(new URL("../demo/", import.meta.url));
const settings: Settings = {
  projectEndpoint: "https://example.services.ai.azure.com/api/projects/test",
  model: "test-model",
  repository: { owner: "example", name: "seat-billing" },
  githubToken: "test-token",
  port: 8088,
};
const issue: Issue = {
  number: 7,
  title: "Do not bill suspended seats",
  body: "Only active seats should be included in the monthly quote.",
};

async function setup(t: test.TestContext, testBehavior?: "mutate" | "ignored") {
  const root = await mkdtemp(join(tmpdir(), "opencode-worker-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const home = join(root, "home");
  const work = join(root, "source");
  const remote = join(root, "remote.git");
  await mkdir(home);
  await mkdir(work);
  await cp(demo, work, { recursive: true });
  if (testBehavior) {
    const manifest = JSON.parse(await readFile(join(work, "package.json"), "utf8"));
    manifest.scripts.test = "node --test && node check.cjs";
    await writeFile(join(work, "package.json"), JSON.stringify(manifest));
    if (testBehavior === "mutate") {
      await writeFile(join(work, "check.cjs"), "require('fs').appendFileSync('quote.js', '\\n// changed by tests\\n');\n");
    } else {
      await writeFile(join(work, ".gitignore"), "local-helper.tmp\n");
      await writeFile(join(work, "check.cjs"), "if (!require('fs').existsSync('local-helper.tmp')) throw Error('missing local helper');\n");
    }
  }
  await writeFile(join(work, "environment.test.js"), [
    'import assert from "node:assert/strict";',
    'import test from "node:test";',
    'test("test process has no GitHub token", () => {',
    '  assert.equal(process.env.GITHUB_TOKEN, undefined);',
    '  assert.equal(process.env.GIT_CONFIG_VALUE_2, undefined);',
    "});",
  ].join("\n"));
  const env = { ...process.env, HOME: home, GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: "/dev/null" };
  const git = async (args: string[], cwd = root) => (await exec("git", args, { cwd, env })).stdout;
  await git(["init", "--bare", "--initial-branch=main", remote]);
  await git(["init", "--initial-branch=main", work]);
  await git(["add", "-A"], work);
  await git([
    "-c", "user.name=Test",
    "-c", "user.email=test@example.com",
    "commit", "-m", "Initial seat billing fixture",
  ], work);
  await git(["push", remote, "main"], work);

  class FakeGitHub implements GitHubApi {
    pullRequest: PullRequest | undefined;
    createCalls = 0;
    failCreate = false;
    moved = false;
    moveAfterCreate = false;

    async getRepository() { return { defaultBranch: "main" }; }
    async getIssue() { return issue; }
    async findPullRequest() { return this.pullRequest; }
    async getBranchCommit(number: number) {
      const ref = `refs/heads/${issueBranch(number)}`;
      try {
        await git(["--git-dir", remote, "show-ref", "--verify", "--quiet", ref]);
      } catch (error) {
        if ((error as { code?: number }).code === 1) return undefined;
        throw error;
      }
      const message = (await git(["--git-dir", remote, "log", "-1", "--format=%B", ref])).trim();
      const sha = this.moved
        ? "f".repeat(40)
        : (await git(["--git-dir", remote, "rev-parse", ref])).trim();
      return { sha, message };
    }
    async createDraftPullRequest() {
      this.createCalls++;
      if (this.failCreate) throw new Error("simulated GitHub failure");
      const commit = await this.getBranchCommit(7);
      assert.ok(commit);
      this.pullRequest = {
        number: 42,
        state: "open",
        draft: true,
        headSha: commit.sha,
        url: "https://github.com/example/seat-billing/pull/42",
      };
      if (this.moveAfterCreate) this.moved = true;
      return this.pullRequest;
    }
  }
  return { root, work, remote, git, github: new FakeGitHub() };
}

async function fixQuote(_settings: Settings, _issue: Issue, workspace: string) {
  await writeFile(
    join(workspace, "quote.js"),
    'export function monthlySeatCost(seats, pricePerSeat) {\n  return seats.filter((seat) => seat.status === "active").length * pricePerSeat;\n}\n',
  );
}

test("publishes the tested seat-billing fix as a draft PR", async (t) => {
  const fixture = await setup(t);
  const previous = process.env.GITHUB_TOKEN;
  process.env.GITHUB_TOKEN = "parent-secret";
  t.after(() => {
    if (previous === undefined) delete process.env.GITHUB_TOKEN;
    else process.env.GITHUB_TOKEN = previous;
  });
  let workspace = "";
  const stages: string[] = [];
  const result = await runWorker(settings, 7, new AbortController().signal, (step) => stages.push(step), {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: async (config, workIssue, directory, configDirectory, signal) => {
      workspace = directory;
      await fixQuote(config, workIssue, directory);
      signal.throwIfAborted();
      assert.notEqual(configDirectory, directory);
    },
  });

  assert.equal(result.status, "created");
  assert.equal(fixture.github.createCalls, 1);
  assert.ok(stages.includes("Running npm test."));
  const committed = await fixture.git([
    "--git-dir", fixture.remote, "show", `${issueBranch(7)}:quote.js`,
  ]);
  assert.match(committed, /seat\.status === "active"/);
  assert.match((await fixture.github.getBranchCommit(7))?.message ?? "", /FHA-OpenCode-Test: npm test/);
  await assert.rejects(readFile(join(dirname(workspace), "workspace", "quote.js")), { code: "ENOENT" });
});

test("does not publish when the candidate still fails npm test", async (t) => {
  const fixture = await setup(t);
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: async (_config, _issue, workspace) => {
      await writeFile(join(workspace, "quote.js"), 'export function monthlySeatCost(seats, price) { return seats.length * price; }\n');
    },
  }), /monthly quote excludes suspended seats/);
  assert.equal(await fixture.github.getBranchCommit(7), undefined);
  assert.equal(fixture.github.createCalls, 0);
});

test("rejects a changed test script and changes made during testing", async (t) => {
  const changedScript = await setup(t);
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: changedScript.github,
    remoteUrl: changedScript.remote,
    allowFileProtocol: true,
    runAgent: async (_config, _issue, workspace) => {
      const path = join(workspace, "package.json");
      const manifest = JSON.parse(await readFile(path, "utf8"));
      manifest.scripts.test = "echo tests skipped";
      await writeFile(path, JSON.stringify(manifest));
    },
  }), /changed the npm test script/);
  assert.equal(await changedScript.github.getBranchCommit(7), undefined);

  const changedTree = await setup(t, "mutate");
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: changedTree.github,
    remoteUrl: changedTree.remote,
    allowFileProtocol: true,
    runAgent: fixQuote,
  }), /changed during testing/);
  assert.equal(await changedTree.github.getBranchCommit(7), undefined);
});

test("tests a clean clone rather than ignored files left in the model workspace", async (t) => {
  const fixture = await setup(t, "ignored");
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: async (config, workIssue, workspace) => {
      await fixQuote(config, workIssue, workspace);
      await writeFile(join(workspace, "local-helper.tmp"), "unpublished file");
    },
  }), /missing local helper/);
  assert.equal(await fixture.github.getBranchCommit(7), undefined);
});

test("recovers a pushed branch after PR creation fails without rerunning OpenCode", async (t) => {
  const fixture = await setup(t);
  fixture.github.failCreate = true;
  let agentRuns = 0;
  const options = {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: async (config: Settings, workIssue: Issue, directory: string) => {
      agentRuns++;
      await fixQuote(config, workIssue, directory);
    },
  };
  await assert.rejects(
    runWorker(settings, 7, new AbortController().signal, () => {}, options),
    /simulated GitHub failure/,
  );
  assert.ok(await fixture.github.getBranchCommit(7));
  fixture.github.failCreate = false;
  const stages: string[] = [];
  const result = await runWorker(settings, 7, new AbortController().signal, (step) => stages.push(step), options);
  assert.equal(result.status, "recovered");
  assert.equal(agentRuns, 1);
  assert.ok(stages.includes("Retesting a previously published branch."));
  assert.ok(stages.includes("Running npm test."));
  assert.equal((await runWorker(settings, 7, new AbortController().signal, () => {}, options)).status, "existing");
  assert.equal(fixture.github.createCalls, 2);
});

test("returns a closed PR when its head branch has been deleted", async (t) => {
  const fixture = await setup(t);
  fixture.github.pullRequest = {
    number: 42,
    state: "closed",
    draft: false,
    headSha: "a".repeat(40),
    url: "https://github.com/example/seat-billing/pull/42",
  };
  const result = await runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
    runAgent: async () => { throw new Error("OpenCode should not run for an existing PR"); },
  });
  assert.deepEqual(result, { status: "existing", pullRequest: fixture.github.pullRequest });
  assert.equal(fixture.github.createCalls, 0);
});

test("rejects an open PR whose head branch is missing", async (t) => {
  const fixture = await setup(t);
  fixture.github.pullRequest = {
    number: 42,
    state: "open",
    draft: true,
    headSha: "a".repeat(40),
    url: "https://github.com/example/seat-billing/pull/42",
  };
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
  }), /differs from its PR head/);
  assert.equal(fixture.github.createCalls, 0);
});

test("rejects a closed PR whose existing head branch has moved", async (t) => {
  const fixture = await setup(t);
  await fixture.git(["push", fixture.remote, `HEAD:refs/heads/${issueBranch(7)}`], fixture.work);
  const commit = await fixture.github.getBranchCommit(7);
  assert.ok(commit);
  fixture.github.pullRequest = {
    number: 42,
    state: "closed",
    draft: false,
    headSha: commit.sha,
    url: "https://github.com/example/seat-billing/pull/42",
  };
  fixture.github.moved = true;
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
  }), /differs from its PR head/);
  assert.equal(fixture.github.createCalls, 0);
});

test("retests a changed recovery branch before opening a PR", async (t) => {
  const fixture = await setup(t);
  fixture.github.failCreate = true;
  const options = {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: fixQuote,
  };
  await assert.rejects(
    runWorker(settings, 7, new AbortController().signal, () => {}, options),
    /simulated GitHub failure/,
  );
  await fixture.git(["fetch", fixture.remote, issueBranch(7)], fixture.work);
  await fixture.git(["switch", "-c", "modified-recovery", "FETCH_HEAD"], fixture.work);
  await writeFile(
    join(fixture.work, "quote.js"),
    "export function monthlySeatCost(seats, price) { return seats.length * price; }\n",
  );
  await fixture.git(["add", "quote.js"], fixture.work);
  await fixture.git([
    "-c", "user.name=Test",
    "-c", "user.email=test@example.com",
    "commit", "-m", "Change the candidate", "-m", commitMarker(settings.repository, 7),
  ], fixture.work);
  await fixture.git(["push", fixture.remote, `HEAD:refs/heads/${issueBranch(7)}`], fixture.work);
  fixture.github.failCreate = false;

  await assert.rejects(
    runWorker(settings, 7, new AbortController().signal, () => {}, options),
    /monthly quote excludes suspended seats/,
  );
  assert.equal(fixture.github.createCalls, 1);
});

test("refuses a recovery branch that changes the npm test script", async (t) => {
  const fixture = await setup(t);
  const path = join(fixture.work, "package.json");
  const manifest = JSON.parse(await readFile(path, "utf8"));
  manifest.scripts.test = "echo tests skipped";
  await writeFile(path, JSON.stringify(manifest));
  await fixture.git(["add", "package.json"], fixture.work);
  await fixture.git([
    "-c", "user.name=Test",
    "-c", "user.email=test@example.com",
    "commit", "-m", "Skip tests", "-m", commitMarker(settings.repository, 7),
  ], fixture.work);
  await fixture.git(["push", fixture.remote, `HEAD:refs/heads/${issueBranch(7)}`], fixture.work);

  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: async () => { throw new Error("OpenCode should not run during recovery"); },
  }), /changed the npm test script/);
  assert.equal(fixture.github.createCalls, 0);
});

test("refuses an unrelated existing branch and does not publish empty changes", async (t) => {
  const conflict = await setup(t);
  await conflict.git(["push", conflict.remote, `HEAD:refs/heads/${issueBranch(7)}`], conflict.work);
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: conflict.github,
    remoteUrl: conflict.remote,
    allowFileProtocol: true,
    runAgent: fixQuote,
  }), /already exists/);
  assert.equal(conflict.github.createCalls, 0);

  const unchanged = await setup(t);
  const result = await runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: unchanged.github,
    remoteUrl: unchanged.remote,
    allowFileProtocol: true,
    runAgent: async () => {},
  });
  assert.deepEqual(result, { status: "no_changes" });
  assert.equal(await unchanged.github.getBranchCommit(7), undefined);
});

test("does not overwrite a branch created while the agent is working", async (t) => {
  const fixture = await setup(t);
  const initial = (await fixture.git(["rev-parse", "HEAD"], fixture.work)).trim();
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: async (config, workIssue, workspace) => {
      await fixQuote(config, workIssue, workspace);
      await fixture.git(["push", fixture.remote, `HEAD:refs/heads/${issueBranch(7)}`], fixture.work);
    },
  }), /git failed/);
  assert.equal((await fixture.github.getBranchCommit(7))?.sha, initial);
  assert.equal(fixture.github.createCalls, 0);
});

test("reports a branch that moves while the draft PR is created", async (t) => {
  const fixture = await setup(t);
  fixture.github.moveAfterCreate = true;
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: fixQuote,
  }), /branch changed while opening .*pull\/42/);
  assert.equal(fixture.github.createCalls, 1);
  await assert.rejects(runWorker(settings, 7, new AbortController().signal, () => {}, {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: fixQuote,
  }), /differs from its PR head/);
});

test("cancellation removes the temporary workspace and never opens a PR", async (t) => {
  const fixture = await setup(t);
  const controller = new AbortController();
  let ready!: () => void;
  const started = new Promise<void>((resolve) => { ready = resolve; });
  let workspace = "";
  const run = runWorker(settings, 7, controller.signal, () => {}, {
    github: fixture.github,
    remoteUrl: fixture.remote,
    allowFileProtocol: true,
    runAgent: async (_config, _issue, directory, _configDirectory, signal) => {
      workspace = directory;
      ready();
      await new Promise<void>((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      });
    },
  });
  await started;
  controller.abort(new Error("test cancellation"));
  await assert.rejects(run, /test cancellation/);
  await assert.rejects(readFile(join(workspace, "quote.js")), { code: "ENOENT" });
  assert.equal(fixture.github.createCalls, 0);
});
