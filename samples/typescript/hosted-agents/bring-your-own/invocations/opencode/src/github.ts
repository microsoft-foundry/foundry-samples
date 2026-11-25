import { commitMarker, issueBranch, repositoryName, type Repository } from "./config.js";

export interface Issue {
  number: number;
  title: string;
  body: string;
}

export interface PullRequest {
  number: number;
  url: string;
  state: string;
  draft: boolean;
  headSha: string;
}

export interface BranchCommit {
  sha: string;
  message: string;
}

export interface RepositoryInfo {
  defaultBranch: string;
}

export interface GitHubApi {
  getRepository(signal: AbortSignal): Promise<RepositoryInfo>;
  getIssue(number: number, signal: AbortSignal): Promise<Issue>;
  findPullRequest(number: number, signal: AbortSignal): Promise<PullRequest | undefined>;
  getBranchCommit(number: number, signal: AbortSignal): Promise<BranchCommit | undefined>;
  createDraftPullRequest(issue: Issue, base: string, signal: AbortSignal): Promise<PullRequest>;
}

export class GitHub implements GitHubApi {
  private readonly path: string;

  constructor(
    private readonly repository: Repository,
    private readonly token: string,
    private readonly fetcher: typeof fetch = fetch,
  ) {
    this.path = `/repos/${encodeURIComponent(repository.owner)}/${encodeURIComponent(repository.name)}`;
  }

  private async request(
    path: string,
    signal: AbortSignal,
    options: { method?: string; body?: object; allowNotFound?: boolean } = {},
  ): Promise<unknown> {
    const response = await this.fetcher(`https://api.github.com${path}`, {
      method: options.method ?? "GET",
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${this.token}`,
        "content-type": "application/json",
        "user-agent": "foundry-opencode-hosted-sample",
        "x-github-api-version": "2022-11-28",
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      redirect: "error",
      signal,
    });
    if (response.status === 404 && options.allowNotFound) return undefined;
    if (!response.ok) {
      throw new Error(`GitHub API ${options.method ?? "GET"} ${path} failed with HTTP ${response.status}.`);
    }
    return response.json();
  }

  async getRepository(signal: AbortSignal): Promise<RepositoryInfo> {
    const data = await this.request(this.path, signal) as { default_branch?: unknown };
    if (typeof data.default_branch !== "string" || !data.default_branch) {
      throw new Error("GitHub did not return a default branch.");
    }
    return { defaultBranch: data.default_branch };
  }

  async getIssue(number: number, signal: AbortSignal): Promise<Issue> {
    const data = await this.request(`${this.path}/issues/${number}`, signal) as {
      number?: unknown;
      title?: unknown;
      body?: unknown;
      state?: unknown;
      pull_request?: unknown;
    };
    if (data.number !== number || typeof data.title !== "string" || data.state !== "open" || data.pull_request) {
      throw new Error(`Issue ${number} must be an open GitHub issue, not a pull request.`);
    }
    if (data.body !== null && typeof data.body !== "string") {
      throw new Error(`GitHub returned an invalid body for issue ${number}.`);
    }
    return { number, title: data.title.slice(0, 256), body: (data.body ?? "").slice(0, 16_000) };
  }

  async findPullRequest(number: number, signal: AbortSignal): Promise<PullRequest | undefined> {
    const query = new URLSearchParams({
      state: "all",
      head: `${this.repository.owner}:${issueBranch(number)}`,
      per_page: "100",
    });
    const data = await this.request(`${this.path}/pulls?${query}`, signal);
    if (!Array.isArray(data)) throw new Error("GitHub returned an invalid pull-request list.");
    if (data.length === 0) return undefined;
    const pull = data.find((item) => item?.state === "open") ?? data[0];
    return this.parsePullRequest(pull);
  }

  async getBranchCommit(number: number, signal: AbortSignal): Promise<BranchCommit | undefined> {
    const branch = issueBranch(number).split("/").map(encodeURIComponent).join("/");
    const ref = await this.request(`${this.path}/git/ref/heads/${branch}`, signal, {
      allowNotFound: true,
    }) as { object?: { sha?: unknown } } | undefined;
    if (!ref) return undefined;
    if (typeof ref.object?.sha !== "string" || !/^[a-f0-9]{40}$/i.test(ref.object.sha)) {
      throw new Error("GitHub returned an invalid branch commit.");
    }
    const commit = await this.request(`${this.path}/git/commits/${ref.object.sha}`, signal) as {
      message?: unknown;
    };
    if (typeof commit.message !== "string") throw new Error("GitHub returned an invalid commit message.");
    return { sha: ref.object.sha, message: commit.message };
  }

  async createDraftPullRequest(issue: Issue, base: string, signal: AbortSignal): Promise<PullRequest> {
    const data = await this.request(`${this.path}/pulls`, signal, {
      method: "POST",
      body: {
        title: `Fix #${issue.number}: ${issue.title.replace(/[\r\n]+/g, " ").slice(0, 200)}`,
        head: issueBranch(issue.number),
        base,
        draft: true,
        body: [
          `Addresses #${issue.number} using OpenCode on Foundry Hosted Agents.`,
          "",
          "Review the changes and run your repository's CI before merging.",
          "",
          "_This comment was generated by an AI assistant on behalf of the PR author._",
        ].join("\n"),
      },
    });
    return this.parsePullRequest(data);
  }

  private parsePullRequest(value: unknown): PullRequest {
    const data = value as { number?: unknown; state?: unknown; draft?: unknown; head?: { sha?: unknown } };
    if (
      !data ||
      typeof data.number !== "number" ||
      !Number.isSafeInteger(data.number) ||
      typeof data.state !== "string" ||
      typeof data.draft !== "boolean" ||
      typeof data.head?.sha !== "string" ||
      !/^[a-f0-9]{40}$/i.test(data.head.sha)
    ) {
      throw new Error("GitHub returned an invalid pull request.");
    }
    return {
      number: data.number,
      state: data.state,
      draft: data.draft,
      headSha: data.head.sha,
      url: `https://github.com/${repositoryName(this.repository)}/pull/${data.number}`,
    };
  }
}

export function isRecoverableBranch(
  message: string,
  repository: Repository,
  issueNumber: number,
): boolean {
  return message.includes(commitMarker(repository, issueNumber));
}
