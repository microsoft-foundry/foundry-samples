# Contributing Agent Code Samples to Foundry Agent Catalog
Thank you for your interest in contributing Agent Code Samples to the Foundry Agent Catalog repository!

> ⚠️ **Important**  
> When you submit your agent sample(s) to the GitHub "3P-agent-samples” file for availability from the Azure AI Foundry Agent Catalog, you are acknowledging that you are responsible for the submitted content and, as between you and Microsoft, Microsoft is not responsible for any liability that may arise from publication of your agent sample(s) for use by Azure AI Foundry customers.

> The agent code samples in the Foundry Agent Catalog is a curated list. Inclusion of a third-party contributed agent code sample is at the discretion of the Agent Service team that will be reviewing and approving the code sample.

## 🚀 What to Include

Each Agent Sample includes:

Mandatory:
- `README.md` — Overview, setup, usage, and customization
- `template.py` — Agent sample code using the following languages and the SDKs:

  A. For Azure AI Agent Service templates:
    1. (Required) Python: [Azure AI Projects client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-projects-readme?view=azure-python-preview#create-agent-with-openapi)
    2. .NET/C#: [Azure AI Projects client library for .NET - Azure for .NET Developers | Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.projects-readme?view=azure-dotnet-preview)
    3. JavaScript: [Azure AI Projects client library for JavaScript | Microsoft Learn](https://learn.microsoft.com/en-us/javascript/api/overview/azure/ai-projects-readme?view=azure-node-preview)
  
  B. For Semantic Kernel templates:
    1. (Required) Python: [Getting started with Semantic Kernel for Python | Microsoft Learn]([https://learn.microsoft.com/en-us/python/api/overview/azure/ai-projects-readme?view=azure-python-preview#create-agent-with-openapi](https://learn.microsoft.com/en-us/semantic-kernel/get-started/quick-start-guide?pivots=programming-language-python))
    2. C#: [Getting started with Semantic Kernel for C# | Microsoft Learn]([https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.projects-readme?view=azure-dotnet-preview](https://learn.microsoft.com/en-us/semantic-kernel/get-started/quick-start-guide?pivots=programming-language-csharp))
    3. Java: [Getting started with Semantic Kernel for Java | Microsoft Learn]([https://learn.microsoft.com/en-us/javascript/api/overview/azure/ai-projects-readme?view=azure-node-preview](https://learn.microsoft.com/en-us/semantic-kernel/get-started/quick-start-guide?pivots=programming-language-java))
- `LICENSE` — License file at the sample folder level

Optional (as appropriate)
- `deploy.bicep` — Bicep script for deploying the agent and tools resources
- `sample_data` — Example inputs, outputs and/or mock datasets
- `assets` — Diagrams, sample screenshots

## 📦 Folder Structure
- Folder names should be lowercase, hyphen-separated
  - Example: sales-lead-qualification-agent
- No spaces or underscores
- All samples must follow this folder structure:

```text
/<agent-name>/

├── README.md
├── python/                        # Python-specific implementation
│   ├── template.py
│   ├── deploy.bicep (optional)
│   ├── src/
│   │   └── custom_logic.py
│   ├── tests/ (optional)
│   │   └── test_agent.py
│   └── sample_data/
│       ├── example_input.json
│       └── example_output.json
├── csharp/                        # C# implementation
│   ├── template.csproj
│   ├── deploy.bicep (optional)
│   ├── src/
│   │   └── AgentLogic.cs
│   │   └── Tools/
│   │       └── CustomTool.cs
│   ├── tests/ (optional)
│   │   └── AgentTests.cs
├── assets/ (optional)
│   ├── architecture.png
│   ├── knowledge_example.json
│   └── logo.svg (required if not Microsoft-authored)
└── LICENSE

```

## 📄 README.md Expectations

Each sample must include a well-documented README.md with: 

**- Agent Name and Summary**
A short description of what the agent does

**- Use Cases**
2-3 Practical business scenarios where the agent is useful

**- Architecture Overview**
Explanation of how the agent works, with a diagram (recommended)

**- Setup Instructions**
How to clone the repo, configure variables, and deploy using deploy.bicep, if applicable

**- Configuration Guide**
Table or list of key parameters with descriptions

**- Sample Data Instructions**
Description of how to use the `sample_data/` folder to validate the agent

**- Example Agent Interaction**
A quick example of how a user might interact with the Agent System:

**- Customization Tips**
Optional Instructions for extending the agent

**License**
Specify and include a license in the agent folder


## 📤 Submission Process
- Fork this repository
- Create a new folder under root using your agent name
- Add all required files as described above
- Open a pull request with:
  - A clear title (e.g., `Add Retail Inventory Management Agent`)
  - A brief description of the agent

We will perform a lightweight review for:
-   Structure and completeness
-   Deployment sanity
-   Documentation quality
