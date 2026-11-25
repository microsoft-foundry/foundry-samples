<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# OpenCode repository-maintenance agent

This sample hosts [OpenCode](https://github.com/anomalyco/opencode) on Foundry Hosted Agents.
Give it an issue number in one configured GitHub repository. It reads the issue, clones the
repository, uses OpenCode's file tools to propose a fix, runs `npm test`, and opens a **draft**
pull request if the test succeeds. A maintainer must review the changes and CI before merging.

Clients use the Foundry **Invocations** protocol. The agent calls the Foundry **Responses** API
for model inference using its managed identity or a local Azure credential. OpenCode runs
headlessly; model shell, web, and interactive approval tools are disabled.

> **Trust boundary:** This is not a sandbox. The model, the repository, and `npm test` run in
> the same container as the agent, and test scripts can execute arbitrary code. Use only a
> repository, issues, and test scripts you trust. Use an isolated test repository and a
> short-lived, repository-scoped GitHub token. Restrict who can invoke the agent. Review the
> draft PR: a passing test does not prove that the fix or modified tests are correct.

## Prerequisites

- Node.js 26.4.0 or later, Git, and npm.
- A Foundry project with a tool-capable model deployment and an identity authorized to use it.
- The [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
  and its Foundry agents extension for deployment.
- A trusted GitHub repository with an open issue and a self-contained `npm test` script. This
  sample does not install dependencies in the target repository; adapt the workflow if its
  tests need a separate setup step.
- A short-lived fine-grained token scoped to that repository with **Contents: read and write**,
  **Issues: read**, and **Pull requests: read and write** permissions. The repository must
  permit creation of pull requests. Never commit the token.

## Try the seat-billing example

The `demo/` directory is a small repository fixture. Its monthly quote currently charges for
suspended seats, and `npm test` fails until that bug is fixed. Copy the contents of `demo/`
into a new isolated GitHub repository you own, push its default branch, and open an issue:

> **Title:** Do not bill suspended seats
>
> **Body:** `monthlySeatCost` should include only seats whose status is `active`. The existing
> test demonstrates the overcharge. Fix the calculation without changing the `npm test` script.

Use the new repository's `owner/name` and the issue number below. Do not use a production
repository for this demonstration.

## Run locally

From this directory, authenticate to Azure and set the variables in your shell:

```bash
az login
export FOUNDRY_PROJECT_ENDPOINT="https://YOUR-ACCOUNT.services.ai.azure.com/api/projects/YOUR-PROJECT"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="YOUR-DEPLOYMENT"
export GITHUB_REPOSITORY="YOUR-OWNER/YOUR-TEST-REPOSITORY"
export GITHUB_TOKEN="YOUR-SHORT-LIVED-REPOSITORY-TOKEN"
npm ci
npm run build
npm start
```

In another terminal, substitute your issue number:

```bash
curl -N http://localhost:8088/invocations \
  -H 'content-type: application/json' \
  -d '{"issue":1}'
```

Plain text such as `Fix issue #1`, or JSON with a single `input` or `message` field containing
that text, is also accepted. The response is a server-sent event stream: `started`, `progress`,
and either `complete` or `error`. A `created` or `recovered` result contains the draft PR URL.
`existing` returns a matching PR without rerunning tests and includes its state and draft status;
`no_changes` means OpenCode made no tracked changes and no PR was created. HTTP validation
errors are returned before streaming; after streaming begins, inspect the final event for success
or failure.

## Deploy and invoke

To use an existing Foundry project, model deployment, and Azure Container Registry, configure
the `ai-project` service in your local copy of `azure.yaml` to reference that project instead
of provisioning the default model. Leave the agent service unchanged:

```yaml
  ai-project:
    host: azure.ai.project
    endpoint: https://YOUR-ACCOUNT.services.ai.azure.com/api/projects/YOUR-PROJECT
```

Then configure an azd environment from this directory. The GitHub token is the short-lived
token described above; the local `GITHUB_TOKEN` environment variable from the previous section
can be reused. Replace the placeholders before running:

```bash
umask 077
azd auth login
azd env new opencode
azd env set FOUNDRY_PROJECT_ENDPOINT "https://YOUR-ACCOUNT.services.ai.azure.com/api/projects/YOUR-PROJECT"
azd env set AZURE_SUBSCRIPTION_ID "YOUR-SUBSCRIPTION-ID"
azd env set AZURE_RESOURCE_GROUP "YOUR-RESOURCE-GROUP"
azd env set AZURE_AI_ACCOUNT_NAME "YOUR-ACCOUNT"
azd env set AZURE_AI_PROJECT_NAME "YOUR-PROJECT"
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT "YOUR-REGISTRY.azurecr.io"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "YOUR-MODEL-DEPLOYMENT"
azd env set GITHUB_REPOSITORY "YOUR-OWNER/YOUR-TEST-REPOSITORY"
printf 'GITHUB_TOKEN=%s\n' "$GITHUB_TOKEN" | azd env set --file /dev/stdin
azd deploy
azd ai agent invoke --protocol invocations "Fix issue #1"
```

The hosted agent identity needs project permissions for model inference. Foundry injects
`FOUNDRY_PROJECT_ENDPOINT` into the container; for local use, `AZURE_AI_PROJECT_ENDPOINT` is
also accepted when `FOUNDRY_PROJECT_ENDPOINT` is not set.

The included `azure.yaml` can alternatively provision a project and default model with
`azd provision`. The deployment environment contains sensitive values: protect its local files
and access to the hosted agent configuration, and rotate or revoke the token after the
demonstration. Clearing the local azd value does not remove it from an existing deployment.

## Behavior and limits

- `GET /readiness` reports container readiness. `POST /invocations` accepts one issue number,
  up to 16 KiB per request. One job runs at a time per container; additional requests receive
  HTTP 429. Jobs time out after 10 minutes and are canceled when the client disconnects.
- Each job uses a fresh temporary clone and deletes it afterward; workspace changes and OpenCode
  session history do **not** persist between invocations, including within a client session.
- The sample stages the candidate tree, applies it to a clean clone for testing, and rejects a
  changed `npm test` script or tracked changes that remain after testing. It applies the patch to
  another clean clone and checks the tree hash before committing and pushing. It does not
  force-push. Tests can still temporarily modify and restore files while they run.
- A deterministic branch and existing-PR lookup support **best-effort** retry recovery. A
  branch bearing this sample's commit marker can be retested to finish opening a PR after an
  interrupted push; a branch without the marker is rejected. A create-only Git lease prevents
  overwriting a concurrently created branch, and the branch and PR head are checked around PR
  creation and when returning an existing PR. External writers can still change a branch
  afterward; this is not an exactly-once guarantee.
- OpenCode project-configuration discovery is disabled, a policy denies configured plugins, and
  the model is restricted to workspace file tools. The SDK can still load system-managed
  configuration and policies; review those before deployment. These controls do not isolate a
  malicious repository or test process.
