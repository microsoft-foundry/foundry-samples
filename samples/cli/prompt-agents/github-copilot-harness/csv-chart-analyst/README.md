# CSV Chart Analyst

A GitHub Copilot harness Prompt Agent sample for a complete native file workflow: upload a CSV,
attach it to a request, analyze it in the harness workspace, generate a PNG, upload the output to
Foundry Files, and download it through the client.

One `azd up` creates:

- a Microsoft Foundry project and `gpt-5.4-mini` deployment;
- one Prompt Agent using `harness.type: github_copilot_preview`;
- native file-read, file-write, and shell capabilities with all other harness built-ins disabled;
  and
- a post-deploy role assignment granting the Agent identity **Foundry User** at project scope.

See [FINDINGS.md](FINDINGS.md) for the tested behavior and current caveats.

## Prerequisites

- Azure Developer CLI (`azd`) 1.34.2 or later with the Microsoft Foundry extension pack. The sample
  pins `azure.ai.agents` 1.0.0-beta.19.
- Azure CLI authenticated to the target tenant.
- Python 3.9 or later.
- Permission to create Foundry resources, deploy Agent versions, and assign **Foundry User** at
  project scope.

## Deploy

From this folder:

```bash
azd auth login
azd env new csv-chart-analyst-dev \
  --subscription <subscription-id> \
  --location canadacentral
azd up --no-prompt
```

Canada Central is the sample default. Replace `canadacentral` with another supported Foundry region
when needed.

The `postdeploy` hook retrieves the created Agent's `instance_identity.principal_id` and assigns
**Foundry User** on the Foundry project. It doesn't assign the role to the project managed identity.
The role can take several minutes to propagate; retry from a new conversation if output upload
initially returns HTTP 403.

## Run the complete workflow

Create a virtual environment and install the client dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start an interactive conversation:

```bash
python chat.py sample-data/regional-sales.csv
```

Try:

```text
Summarize the data and identify the strongest region.
How did monthly revenue change from January through June?
Create a grouped bar chart of revenue by month and region. Return it as a PNG file.
```

Generated files are downloaded to `outputs/`.

For a repeatable non-interactive test:

```bash
python chat.py sample-data/regional-sales.csv \
  --prompt "Analyze the CSV, identify the region with the highest total revenue, and create a grouped bar chart of monthly revenue by region as a downloadable PNG."
```

The client uploads the CSV to the project Files API and includes its file ID as an `input_file` in
the Responses request. The harness stages the attachment before the model starts. The Agent uses
shell and Python to inspect the CSV. If the plotting library is missing, it installs the minimum
package with pip, writes the PNG to the runtime-provided output directory, and uploads it to Foundry
Files.

The client prefers a project `file_citation` annotation. It also supports builds that return the
uploaded filename and Foundry file ID as `File` and `Download ID` text. It downloads either form
through the project Files API, not the Code Interpreter Containers API.

## Data and security behavior

- The CSV is uploaded with purpose `assistants` to the project-scoped Files API.
- The CSV is attached to each turn in the same conversation. The runtime deduplicates the staged
  file and keeps it available for follow-up analysis.
- Native web and subagent tools are disabled. Shell is enabled, so disabling the separate filesystem
  controls isn't a strict security boundary.
- The output upload runs as the Agent identity and requires **Foundry User** at project scope.
- Uploaded input and generated output files are not deleted automatically. Clean them up according
  to your data-retention requirements.
- The sample doesn't configure or invoke Code Interpreter.

## Supported surfaces

| Step | Included client |
| --- | --- |
| Upload CSV to Foundry Files | Yes |
| Stage `input_file` in the harness workspace | Yes |
| Analyze across turns | Yes |
| Install a missing plotting package | Yes |
| Generate and upload PNG | Yes |
| Download PNG from Foundry Files | Yes |

The included client path was tested end to end. Portal attachment filtering and generated-file UI
behavior can differ by rollout and aren't required by this sample.

The client sends the preview `Foundry-Features` header required by the tested GitHub Copilot harness
endpoint. Replace that preview contract with the released API before publishing this client as a
production pattern.

## Tear down

Delete the complete isolated environment after testing:

```bash
azd down --purge --force --no-prompt
```

The client doesn't delete individual input or output files. Purging the isolated project removes its
Foundry Files; delete local files under `outputs/` separately when they are no longer needed.
