# Microsoft Foundry infrastructure layer

The `microsoft.foundry` provider provisions the Foundry account, project, and sample-specific GPT-5.4
Global Standard deployment declared in `azure.yaml`. The Browser Automation Bicep layer depends on
this layer so it can grant the Foundry project identity access to the Playwright workspace.
