# Hybrid Private Resources Agent Setup

This folder provides a Terraform implementation for a hybrid setup with a mix of private and public resources.

## Overview

This advanced scenario demonstrates:
- Microsoft Foundry with selective private/public access
- Some resources with private endpoints, others public
- Agent setup with hybrid networking
- Complex routing and DNS configuration

## Status

**🚧 PARTIALLY IMPLEMENTED** - This complex scenario requires:

1. Hybrid networking design
2. Selective private endpoint deployment
3. DNS configuration for mixed access
4. Network security group rules
5. Firewall and routing configuration

## Use Cases

- Migration from public to private (gradual transition)
- Development environment (public) vs Production (private)
- Selective resource isolation
- Cost optimization (private only where needed)

## Reference

For implementation guidance, see the Bicep reference:
- `infrastructure-setup-bicep/19-hybrid-private-resources-agent-setup`

## Prerequisites

- Advanced Azure networking knowledge
- Understanding of hybrid networking patterns
- Network security expertise

## Contributing

This is a complex scenario. When implementing:
1. Document the reasoning for public vs private choices
2. Include network diagrams
3. Explain security implications
4. Provide migration guidance

## Documentation

- [Configure private link for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link)
- [azurerm_private_endpoint - Terraform](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/private_endpoint)
- [AzAPI Provider](https://registry.terraform.io/providers/azure/azapi/latest/docs)

`Tags: Hybrid Networking, Private Endpoints, Advanced`
