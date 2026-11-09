---
ai-usage: ai-assisted
---

# Agent Controls samples (preview)

These samples include Microsoft Foundry Agent Controls policy templates, PowerShell management scripts, and a Node.js helper for host integration and evaluation. The helper is sample code, not a product SDK.

- [Read the full guide](./samples/readme.md) for prerequisites, policy templates, configuration, and local checks.
- [Download the samples ZIP](./media/agent-controls-samples.zip?raw=true). The archive contains the nested `samples/` directory.

> [!IMPORTANT]
> Agent Controls is in preview. Live service calls require an Azure AI Content Safety account enabled for the preview in a region enabled for your access. Creating an account doesn't enable preview access.

## Install and test locally

Use Node.js 22 or later with npm. From this package directory (`samples/cli/agent-controls`), install dependencies:

```bash
npm --prefix samples ci
```

After installation succeeds, run the local Node.js tests:

```bash
npm --prefix samples test
```

The Node.js tests use synthetic responses and a loopback server. The [full guide](./samples/readme.md#verify-the-samples-locally) also covers local Rego tests and ARM tests that mock Azure CLI and HTTP calls.

These checks don't validate live service access. The demo and evaluation scripts call the service; management scripts can create or remove Azure resources and publish policies. Review the guide before running those scripts.
