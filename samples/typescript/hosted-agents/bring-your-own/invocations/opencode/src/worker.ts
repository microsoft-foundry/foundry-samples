import { mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runOpenCode } from "./agent.js";
import { runCommand } from "./command.js";
import {
  commitMarker,
  issueBranch,
  repositoryName,
  type Settings,
} from "./config.js";
import {
  GitHub,
  isRecoverableBranch,
  type GitHubApi,
  type Issue,
  type PullRequest,
} from "./github.js";

export type WorkerResult =
  | { status: "created" | "recovered" | "existing"; pullRequest: PullRequest }
  | { status: "no_changes" };

interface WorkerDependencies {
  github?: GitHubApi;
  runAgent?: typeof runOpenCode;
  remoteUrl?: string;
  allowFileProtocol?: boolean;
}

function parseTestScript(contents: string): string {
  let manifest: unknown;
  try {
    manifest = JSON.parse(contents);
  } catch (error) {
    throw new Error("The target repository must have a readable package.json.", { cause: error });
  }
  if (
    !manifest ||
    typeof manifest !== "object" ||
    !("scripts" in manifest) ||
    !manifest.scripts ||
    typeof manifest.scripts !== "object" ||
    !("test" in manifest.scripts) ||
    typeof manifest.scripts.test !== "string" ||
    !manifest.scripts.test.trim()
  ) {
    throw new Error("The target repository must define an npm test script.");
  }
  return manifest.scripts.test;
}

async function testScript(directory: string): Promise<string> {
  let contents: string;
  try {
    contents = await readFile(join(directory, "package.json"), "utf8");
  } catch (error) {
    throw new Error("The target repository must have a readable package.json.", { cause: error });
  }
  return parseTestScript(contents);
}

async function createOrFindPullRequest(
  github: GitHubApi,
  issue: Issue,
  base: string,
  expectedCommit: string,
  signal: AbortSignal,
): Promise<{ pullRequest: PullRequest; created: boolean }> {
  if ((await github.getBranchCommit(issue.number, signal))?.sha !== expectedCommit) {
    throw new Error("The published branch changed before PR creation.");
  }
  let pullRequest: PullRequest;
  let created = true;
  try {
    pullRequest = await github.createDraftPullRequest(issue, base, signal);
  } catch (error) {
    signal.throwIfAborted();
    const existing = await github.findPullRequest(issue.number, signal);
    if (!existing || existing.state !== "open") throw error;
    pullRequest = existing;
    created = false;
  }
  if (
    pullRequest.headSha !== expectedCommit ||
    (await github.getBranchCommit(issue.number, signal))?.sha !== expectedCommit
  ) {
    throw new Error(`The branch changed while opening ${pullRequest.url}; review the draft PR before using it.`);
  }
  return { pullRequest, created };
}

export async function runWorker(
  settings: Settings,
  issueNumber: number,
  signal: AbortSignal,
  progress: (message: string) => void,
  dependencies: WorkerDependencies = {},
): Promise<WorkerResult> {
  const github = dependencies.github ?? new GitHub(settings.repository, settings.githubToken);
  const agent = dependencies.runAgent ?? runOpenCode;
  const existing = await github.findPullRequest(issueNumber, signal);
  if (existing) {
    if ((await github.getBranchCommit(issueNumber, signal))?.sha !== existing.headSha) {
      throw new Error(`The branch for ${existing.url} differs from its PR head; review it before retrying.`);
    }
    return { status: "existing", pullRequest: existing };
  }

  const issue = await github.getIssue(issueNumber, signal);
  const { defaultBranch } = await github.getRepository(signal);
  const previousCommit = await github.getBranchCommit(issueNumber, signal);
  if (previousCommit && !isRecoverableBranch(previousCommit.message, settings.repository, issueNumber)) {
    throw new Error(`Branch ${issueBranch(issueNumber)} already exists without this sample's recovery marker.`);
  }

  const root = await mkdtemp(join(tmpdir(), "foundry-opencode-"));
  try {
    const home = join(root, "home");
    const configDirectory = join(root, "opencode-config");
    const workspace = join(root, "workspace");
    const testWorkspace = join(root, "test");
    const publish = join(root, "publish");
    await mkdir(home);
    await mkdir(configDirectory);
    const baseEnv: NodeJS.ProcessEnv = {
      PATH: process.env.PATH,
      HOME: home,
      TMPDIR: root,
      LANG: "C.UTF-8",
      LC_ALL: "C.UTF-8",
      GIT_CONFIG_NOSYSTEM: "1",
      GIT_CONFIG_GLOBAL: "/dev/null",
      GIT_TERMINAL_PROMPT: "0",
      GIT_ASKPASS: "/bin/false",
      GIT_ALLOW_PROTOCOL: dependencies.allowFileProtocol ? "https:file" : "https",
      GIT_LFS_SKIP_SMUDGE: "1",
      npm_config_userconfig: join(home, "user.npmrc"),
      npm_config_globalconfig: join(home, "global.npmrc"),
    };
    const basicToken = Buffer.from(`x-access-token:${settings.githubToken}`).toString("base64");
    const gitEnv: NodeJS.ProcessEnv = {
      ...baseEnv,
      GIT_CONFIG_COUNT: "3",
      GIT_CONFIG_KEY_0: "credential.helper",
      GIT_CONFIG_VALUE_0: "",
      GIT_CONFIG_KEY_1: "core.hooksPath",
      GIT_CONFIG_VALUE_1: "/dev/null",
      GIT_CONFIG_KEY_2: "http.https://github.com/.extraheader",
      GIT_CONFIG_VALUE_2: `AUTHORIZATION: basic ${basicToken}`,
    };
    const remote = dependencies.remoteUrl ?? `https://github.com/${repositoryName(settings.repository)}.git`;
    const git = (cwd: string, args: string[], input?: string, maxOutput?: number) =>
      runCommand("git", args, {
        cwd,
        env: gitEnv,
        signal,
        input,
        maxOutput,
        secrets: [settings.githubToken, basicToken],
      });

    const testCandidate = async (directory: string, tree: string, originalScript: string) => {
      if (await testScript(directory) !== originalScript) {
        throw new Error("The candidate changed the npm test script; refusing to publish.");
      }
      progress("Running npm test.");
      await runCommand("npm", ["test"], { cwd: directory, env: baseEnv, signal });
      if (await testScript(directory) !== originalScript) {
        throw new Error("The npm test script changed during testing; refusing to publish.");
      }
      await git(directory, ["add", "-A"]);
      if ((await git(directory, ["write-tree"])).trim() !== tree) {
        throw new Error("The repository changed during testing; refusing to publish an untested tree.");
      }
    };

    if (previousCommit) {
      progress("Retesting a previously published branch.");
      await git(root, ["clone", "--no-tags", "--branch", issueBranch(issueNumber), "--", remote, testWorkspace]);
      if ((await git(testWorkspace, ["rev-parse", "HEAD"])).trim() !== previousCommit.sha) {
        throw new Error("The published branch changed before recovery.");
      }
      const base = (await git(testWorkspace, [
        "merge-base", "HEAD", `refs/remotes/origin/${defaultBranch}`,
      ])).trim();
      const originalScript = parseTestScript(await git(testWorkspace, ["show", `${base}:package.json`]));
      const tree = (await git(testWorkspace, ["write-tree"])).trim();
      await testCandidate(testWorkspace, tree, originalScript);
      const result = await createOrFindPullRequest(github, issue, defaultBranch, previousCommit.sha, signal);
      return { status: result.created ? "recovered" : "existing", pullRequest: result.pullRequest };
    }

    progress("Cloning the repository.");
    await git(root, ["clone", "--no-tags", "--branch", defaultBranch, "--", remote, workspace]);
    const baseline = (await git(workspace, ["rev-parse", "HEAD"])).trim();
    const baselineTree = (await git(workspace, ["rev-parse", "HEAD^{tree}"])).trim();
    const originalTestScript = await testScript(workspace);

    progress("OpenCode is preparing a fix.");
    await agent(settings, issue, workspace, configDirectory, signal);
    if (await testScript(workspace) !== originalTestScript) {
      throw new Error("OpenCode changed the npm test script; refusing to publish.");
    }
    await git(workspace, ["add", "-A"]);
    const candidateTree = (await git(workspace, ["write-tree"])).trim();
    if (candidateTree === baselineTree) return { status: "no_changes" };
    const patch = await git(
      workspace,
      ["diff", "--cached", "--binary", "--full-index", "HEAD"],
      undefined,
      8_000_000,
    );

    await git(root, ["clone", "--no-tags", "--branch", defaultBranch, "--", remote, testWorkspace]);
    await git(testWorkspace, ["checkout", "--detach", baseline]);
    await git(testWorkspace, ["apply", "--index", "-"], patch);
    if ((await git(testWorkspace, ["write-tree"])).trim() !== candidateTree) {
      throw new Error("The test tree does not match the candidate tree.");
    }

    await testCandidate(testWorkspace, candidateTree, originalTestScript);

    progress("Publishing the tested changes.");
    await git(root, ["clone", "--no-tags", "--branch", defaultBranch, "--", remote, publish]);
    await git(publish, ["checkout", "--detach", baseline]);
    await git(publish, ["apply", "--index", "-"], patch);
    if ((await git(publish, ["write-tree"])).trim() !== candidateTree) {
      throw new Error("The publication tree does not match the tested tree.");
    }
    await git(publish, [
      "-c", "user.name=Foundry OpenCode sample",
      "-c", "user.email=foundry-opencode-sample@users.noreply.github.com",
      "commit", "-m", `Fix issue #${issueNumber}`, "-m", commitMarker(settings.repository, issueNumber),
    ]);
    const commit = (await git(publish, ["rev-parse", "HEAD"])).trim();
    signal.throwIfAborted();
    const ref = `refs/heads/${issueBranch(issueNumber)}`;
    await git(publish, ["push", `--force-with-lease=${ref}:`, "--", remote, `HEAD:${ref}`]);
    signal.throwIfAborted();
    const result = await createOrFindPullRequest(github, issue, defaultBranch, commit, signal);
    return { status: result.created ? "created" : "existing", pullRequest: result.pullRequest };
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}
