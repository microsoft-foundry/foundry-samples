# 📚 Microsoft Learn Agent

> **Your AI-powered documentation companion** - Instantly access the vast knowledge of Microsoft Learn with intelligent search and contextual answers.

<div align="center">

![Agent Framework](https://img.shields.io/badge/Agent_Framework-1.0.0-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.8+-green?style=for-the-badge)
![Azure AI](https://img.shields.io/badge/Azure_AI-Powered-orange?style=for-the-badge)
![MCP](https://img.shields.io/badge/MCP-Enabled-purple?style=for-the-badge)

</div>

## 🌟 What Makes This Special?

This intelligent agent leverages the power of **Model Context Protocol (MCP)** and **Microsoft Agent Framework** to provide seamless access to Microsoft Learn documentation. Whether you're a developer learning Azure Functions, exploring .NET, or diving into AI services, this agent delivers precise, up-to-date answers from the official Microsoft documentation.

### ✨ Key Features

- 🔍 **Smart Documentation Search** - Natural language queries across Microsoft Learn
- 🧠 **Context-Aware Responses** - Understands your intent and provides relevant code examples
- 🚀 **Real-Time Access** - Always up-to-date with the latest Microsoft documentation
- 🔧 **Easy Integration** - Drop into any Azure AI project with minimal setup
- 💬 **Interactive Mode** - Ask follow-up questions and get clarifications

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Azure subscription with AI Foundry access
- [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) installed

### 🎯 Commands

Transform your idea into a working agent in seconds:

```bash
# Initialize your project with the AI Foundry starter
azd init --template Azure-Samples/ai-foundry-starter-basic

# Add the Microsoft Learn Agent to your project
azd ai agent init --manifest https://github.com/coreai-microsoft/foundry-golden-path/blob/main/idea-to-proto/01-build-agent-in-code/agent-catalog-code-samples/msft-docs-agent/agent.yaml

# Deploy the agent in Azure AI Foundry
azd up
```

> **💡 Tip:** The `azd` command automatically handles dependency installation and project setup for you!

## 💬 Example Conversations

### Query Azure Functions

```
You: "How do I create an HTTP-triggered Azure Function in Python?"

Agent: "I'll help you create an HTTP-triggered Azure Function in Python! Here's a complete guide:

## Prerequisites
- Azure Functions Core Tools
- Python 3.8-3.11
- Azure CLI

## Step-by-Step Instructions
1. Create a new function app:
   ```bash
   func init MyFunctionApp --python
   cd MyFunctionApp
   ```

2. Create an HTTP trigger function:
   ```bash
   func new --name HttpExample --template "HTTP trigger"
   ```

[Provides complete code example and deployment instructions...]"
```

## 📖 Learn More

- 🔗 [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) - Official SDK documentation
- 🔗 [Model Context Protocol](https://modelcontextprotocol.io/) - Learn about MCP
- 🔗 [Azure AI Foundry](https://learn.microsoft.com/azure/ai-studio/) - Platform documentation
- 🔗 [Microsoft Learn](https://learn.microsoft.com/) - Source of documentation
