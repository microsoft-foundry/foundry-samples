# AdventureWorks SQL Analyst

A GitHub Copilot harness Prompt Agent that explores the AdventureWorksLT sample database through a
read-only Azure SQL managed connector exposed as a Connector Namespace MCP server.

One `azd up` creates:

- a Microsoft Foundry project and `gpt-5.4-mini` deployment;
- an Azure SQL logical server and Basic database seeded with `AdventureWorksLT`;
- a Connector Namespace with a system-assigned managed identity;
- an Azure SQL managed-identity connection and configurable MCP server;
- a Foundry RemoteTool connection authenticated with the project managed identity; and
- a Prompt Agent with four allow-listed SQL MCP tools and a progressive-disclosure analysis Skill.

This sample uses the managed `sql` connector. It does not deploy Data API builder or a hosted SQL MCP
server.

## Prerequisites

- Azure Developer CLI (`azd`) 1.34.2 or later.
- The Microsoft Foundry `azd` extension pack. The sample pins `azure.ai.agents` 1.0.0-beta.19.
- Azure CLI authenticated to the target tenant.
- `sqlcmd` for the post-provision database permission grant.
- Permission to create Microsoft Foundry, Azure SQL, and Connector Namespace resources and to set a
  Microsoft Entra administrator on the SQL logical server.

Install the standalone Go version of `sqlcmd` for your platform.

On macOS:

```bash
brew install sqlcmd
```

On Windows:

```powershell
winget install sqlcmd
```

On Debian or Ubuntu, first add the Microsoft package repository for your distribution, then run:

```bash
sudo apt-get update
sudo apt-get install sqlcmd
```

For repository setup, RPM-based Linux distributions, and direct downloads, see
[Download and install sqlcmd](https://learn.microsoft.com/sql/tools/sqlcmd/sqlcmd-download-install#download-and-install-sqlcmd-go).

## Deploy

From this folder:

```bash
azd auth login
azd env new adventureworks-sql-dev --location canadacentral
azd up
```

Canada Central is the Foundry and Azure SQL default. Replace `canadacentral` with another supported
Foundry and SQL region when needed. The Connector Namespace defaults separately to West Central US
because it isn't available in Canada Central. Override that dependency before deployment with
`azd env set CONNECTOR_LOCATION <supported-region>`. The complete deployment typically takes about
five minutes.

During provisioning, the signed-in user becomes the SQL Microsoft Entra administrator. The
post-provision hook creates a contained database user for the Connector Namespace identity and grants
only `db_datareader` and `VIEW DEFINITION`. It does not grant database write roles.

For the one-time local grant, the hook first tries `sqlcmd`. If the Azure SQL firewall blocks the
connection, its error identifies the client IP. The hook extracts and validates that IPv4 address,
creates a temporary `AllowDeployerIp` server firewall rule, and removes the rule before the hook
exits, including after an error. The sample doesn't call a third-party IP-discovery service.

To skip automatic discovery, set an explicit address before deployment:

```bash
azd env set DEPLOYER_IP_ADDRESS "<your-public-ipv4-address>"
```

You can also add your current client IP through the Azure SQL server's **Networking** page and omit
the variable. If `sqlcmd` fails for a reason that doesn't contain an unambiguous client IPv4 address,
the hook stops and asks you to use one of these explicit paths.

## Try it

Open **AdventureWorks SQL Analyst** in the Foundry agent playground and try:

```text
Which five products have the highest list price? Include product name, product number, color, and price.
```

```text
Summarize sales by product category and explain the three largest categories.
```

```text
Which customers have placed the largest orders? Return at most ten rows.
```

For a command-line smoke test in a fresh conversation:

```bash
azd ai agent invoke adventureworks-sql-analyst \
  "Which five products have the highest list price? Include product name, product number, color, and price." \
  --new-session --new-conversation --timeout 600 --no-prompt
```

## Skill structure

The `adventureworks-analysis` Skill demonstrates progressive disclosure:

```text
skills/adventureworks-analysis/
  SKILL.md
  references/
    schema.md
    products.md
    sales.md
    customers.md
```

`SKILL.md` is a short router. It tells the agent which focused reference to load for each question,
so product questions do not consume customer and sales guidance unnecessarily. The references encode
verified joins, metric definitions, bounded query patterns, and dataset caveats. The agent enables
the harness's read-only filesystem capability so it can open only the selected reference; shell,
filesystem writes, native web access, and subagents remain disabled.

## Security boundary

The MCP server fixes the SQL server and database in its configuration. The agent can list tables,
read rows, read one row, and submit native SQL queries, but the Connector Namespace identity has only
read permissions in the database. Agent instructions further restrict generated SQL to bounded
`SELECT` statements.

The SQL firewall allows Azure services so the managed connector can reach the public database
endpoint. When `DEPLOYER_IP_ADDRESS` is set, the post-provision hook temporarily permits that one IP
for the local SQL grant and removes the rule afterward.

## Clean up

From this sample folder, remove the isolated environment when you finish:

```bash
azd down --purge --force --no-prompt
```

## References

- [Connector Namespace overview](https://learn.microsoft.com/azure/connector-namespace/connector-namespace-overview)
- [SQL Server managed connector](https://learn.microsoft.com/connectors/sql/)
- [MCP authentication in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication)
- [Create an Azure SQL sample database](https://learn.microsoft.com/azure/azure-sql/database/single-database-create-bicep-quickstart)
- [Download and install sqlcmd](https://learn.microsoft.com/sql/tools/sqlcmd/sqlcmd-download-install)
