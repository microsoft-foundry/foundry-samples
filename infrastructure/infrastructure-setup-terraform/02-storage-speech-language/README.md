# Azure Cognitive Services Integration Examples

This folder contains examples for integrating Microsoft Foundry with other Azure Cognitive Services:

- **Azure Storage Account**: For storing files and data
- **Azure Speech Services**: For speech-to-text and text-to-speech capabilities
- **Azure Language Services**: For natural language processing

## Overview

These are reference examples showing how to create connections between Microsoft Foundry and other Azure Cognitive Services. Each example demonstrates configuring the required resources and establishing connections.

## Prerequisites

- An existing Microsoft Foundry account
- Azure Storage, Speech, or Language service resources
- Appropriate RBAC permissions

## Usage

These examples can be adapted and integrated into your Terraform configurations. Modify the variables to match your resource names and requirements.

## Status

This folder now includes a full Terraform sample with:
- Microsoft Foundry account configured for user-owned storage
- Microsoft Foundry project under the account
- Optional Speech and Language resource deployment switches
- Storage RBAC wiring for the account identity

## Documentation

- [Microsoft Foundry overview](https://learn.microsoft.com/en-us/azure/ai-foundry/)
- [Azure Storage Account - Terraform](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account)
- [AzAPI Provider](https://registry.terraform.io/providers/azure/azapi/latest/docs)

`Tags: Integration, Storage, Speech, Language Services`
