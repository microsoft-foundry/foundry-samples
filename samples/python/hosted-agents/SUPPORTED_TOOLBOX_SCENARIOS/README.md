# Foundry Toolbox scenarios

Use these guides to configure tools and authentication for a Foundry Toolbox.

| Scenario | Guide |
|----------|-------|
| Built-in tools | [Web search, code interpreter, file search, Azure AI Search, Bing Custom Search, and browser automation](tools/built-in-tools.md) |
| MCP, unauthenticated | [Public MCP server](tools/mcp-unauthenticated.md) |
| MCP, key-based | [Static key in a request header](tools/mcp-key-auth.md) |
| MCP, Microsoft Entra | [Agent Identity or Project Managed Identity](tools/mcp-microsoft-entra.md) |
| MCP, OAuth Identity Passthrough | [Custom OAuth app](tools/mcp-oauth-custom.md) |
| MCP, managed OAuth | [Foundry-managed connector](tools/mcp-oauth-managed.md) |
| MCP, user Entra token | [User token passthrough](tools/mcp-user-entra-token.md) |
| MCP skills | [Skills exposed through MCP](tools/mcp-skills.md) |
| OpenAPI | [REST API from an OpenAPI 3.x specification](tools/openapi.md) |
| A2A | [Agent-to-Agent delegation sample workflow](tools/a2a.md) |

## Create the toolbox

Choose a scenario guide above first. It describes the tool-specific configuration and any connection,
resource, or authentication prerequisites.

### Foundry Toolkit in VS Code

1. Sign in to the **Foundry Toolkit** and open **Tool Catalog**.
2. On the **Toolboxes** tab, select **Create Your Toolbox**.
3. In the **Included** panel, select **+ Add** and choose the tool described by the scenario guide.
4. Complete the tool configuration, name the toolbox, and select **Publish**.
5. Open the published toolbox and copy its MCP endpoint for clients that connect by endpoint.

### `azd` CLI

Use `azd` 1.34.2 or later and install the unified Foundry extension bundle with
`azd ext install microsoft.foundry`.

Each scenario guide provides the required `toolbox.yaml` or `azure.yaml` entries.

- For a standalone toolbox, run `azd ai toolbox create <toolbox-name> --from-file
  ./toolbox.yaml`. The first version becomes the default, and the command prints the versioned MCP
  endpoint. Set that endpoint as `TOOLBOX_ENDPOINT` for the consuming agent.
- For a toolbox declared alongside an agent in `azure.yaml`, deploy the toolbox service with `azd`.
  The agent can reference it through `uses` and resolve it by `TOOLBOX_NAME`; no copied endpoint is
  required.

For toolbox lifecycle details, see
[Curate intent-based tools in a toolbox](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox).
