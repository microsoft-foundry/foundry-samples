# Azure AI Agent Service Infrastructure Setup Templates

This directory contains various Infrastructure as Code (IaC) templates coded in Terraform for setting up Azure AI Agent Service environments. Templates are organized in order of complexity and typical deployment progression.

## Azure AI Agent Service Templates

Azure AI Agent Service offers three deployment modes optimized for agent workloads:

- Basic Setup:
    This setup is compatible with OpenAI Assistants and manages agent states using the platform's built-in storage. It includes the same tools and capabilities as the Assistants API, with added support for non-OpenAI models and tools such as Azure AI Search, and Bing.
- Standard Setup:
    Includes everything in the basic setup and fine-grained control over your data by allowing you to use your own Azure resources. All customer data—including files, threads, and vector stores—are stored in your own Azure resources, giving you full ownership and control.
- Standard Setup with Bring Your Own (BYO) Virtual Network:
    Includes everything in the Standard Setup, with the added ability to operate entirely within your own virtual network. This setup supports Bring Your Own Virtual Network (BYO virtual network), allowing for strict control over data movement and helping prevent data exfiltration by keeping traffic confined to your network environment.

### [15a-private-network-standard-agent-setup/](./15a-private-network-standard-agent-setup/README.md)

- Deploys a Network Secured Standard Agent environment:
  - Creates Azure AI Foundry resource and project
  - Automatically deploys gpt-4o
  - Azure resources for storing customer data—Azure Storage, Azure Cosmos DB, and Azure AI Search—are automatically created if existing resources aren't provided.
    - These resources are connected to your project to store files, threads, and vector data.
  - Virtual network is created for you
  - Private DNS Zones are created for you
  - Higher cost with this setup because you also pay for the usage of Azure Storage, Azure AI Search, and Cosmos DB resources

### [15b-private-network-standard-agent-setup-byovnet/](./15b-private-network-standard-agent-setup-byovnet/README.md)

- Deploys a Network Secured Standard Agent environment:
  - Creates Azure AI Foundry resource and project
  - Automatically deploys gpt-4o
  - Azure resources for storing customer data—Azure Storage, Azure Cosmos DB, and Azure AI Search—are automatically created.
    - These resources are connected to your project to store files, threads, and vector data.
  - Bring your own Virtual Network and subnets
  - Bring your own Private DNS Zones
  - Higher cost with this setup because you also pay for the usage of Azure Storage, Azure AI Search, and Cosmos DB resources
