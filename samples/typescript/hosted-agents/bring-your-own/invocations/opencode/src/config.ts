export interface Repository {
  owner: string;
  name: string;
}

export interface Settings {
  projectEndpoint: string;
  model: string;
  repository: Repository;
  githubToken: string;
  port: number;
}

export function loadSettings(env: NodeJS.ProcessEnv): Settings {
  const endpoint = env.FOUNDRY_PROJECT_ENDPOINT ?? env.AZURE_AI_PROJECT_ENDPOINT;
  const model = env.AZURE_AI_MODEL_DEPLOYMENT_NAME;
  const repository = env.GITHUB_REPOSITORY?.match(
    /^([A-Za-z0-9][A-Za-z0-9-]{0,38})\/([A-Za-z0-9_.-]{1,100})$/,
  );
  const githubToken = env.GITHUB_TOKEN;
  const port = Number(env.PORT ?? "8088");

  if (!endpoint) {
    throw new Error("FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT is required.");
  }
  const url = new URL(endpoint);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    !/^\/api\/projects\/[^/]+\/?$/.test(url.pathname)
  ) {
    throw new Error("The project endpoint must be an HTTPS Foundry project endpoint.");
  }
  if (!model || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(model)) {
    throw new Error("AZURE_AI_MODEL_DEPLOYMENT_NAME must be a model deployment name.");
  }
  if (!repository || [".", ".."].includes(repository[2])) {
    throw new Error("GITHUB_REPOSITORY must be an owner/repository name.");
  }
  if (!githubToken || /\s/.test(githubToken)) {
    throw new Error("GITHUB_TOKEN is required and must not contain whitespace.");
  }
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT must be an integer between 1 and 65535.");
  }

  return {
    projectEndpoint: url.toString().replace(/\/$/, ""),
    model,
    repository: { owner: repository[1], name: repository[2] },
    githubToken,
    port,
  };
}

export function repositoryName(repository: Repository): string {
  return `${repository.owner}/${repository.name}`;
}

export function issueBranch(issueNumber: number): string {
  return `fha/opencode-issue-${issueNumber}`;
}

export function commitMarker(repository: Repository, issueNumber: number): string {
  return `FHA-OpenCode-Issue: ${repositoryName(repository)}#${issueNumber}\nFHA-OpenCode-Test: npm test`;
}
