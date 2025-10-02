> [!IMPORTANT]
> We are not accepting new submissions for 3P tools. Thanks for your interest!

# 3p Tool Partner Contributing Guide

> [!IMPORTANT]
> When you submit your tool code sample(s) to the GitHub "3P-tools" file for availability in Azure AI Foundry, you are acknowledging that you are responsible for the submitted content and, as between you and Microsoft, Microsoft is not responsible for any liability that may arise from availability of your code sample(s) for use by Azure AI Foundry customers.

## Who should read this?
This contributing guide is designed for partners who want to bring their APIs as part of the **Azure AI Foundry Agent Service non-Microsoft tools** so that customers can integrate your APIs with Azure AI Foundry Agent service through a tool to retrieve data or integrating with a workflow.

## Prepare your Pull Request (PR)
Your PR needs to create a new folder with the tool name and include the following information: 
- `README.md` (required): follow this [template](./README_template_for_parter.md) as an example and this README file will serve as public documentation for help customers set up and use the tool with your API through Azure AI Foundry Agent service
  - Keep the `Important Note From Microsoft` section as-is at the very top of the file
  - The name, logo, and description in this README file will be used in the Azure AI Foundry Portal user experience and marketing materials.
  - It must include how customers set up an account with your API directly and your customer support contact or website.
  - Customers should be able to follow this README file and successfully use the tool with Azure AI Foundry Agent service.
- `sample code` (required): using at least one of the SDK below
  - (recommended) Python: [Azure AI Projects client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-projects-readme?view=azure-python-preview#create-agent-with-openapi)
  - .NET/C#: [Azure AI Projects client library for .NET - Azure for .NET Developers | Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.projects-readme?view=azure-dotnet-preview)
  - JavaScript: [Azure AI Projects client library for JavaScript | Microsoft Learn](https://learn.microsoft.com/en-us/javascript/api/overview/azure/ai-projects-readme?view=azure-node-preview)
  - Requirements fot the code sample:
    - you should have tested the code sample works end to end with the OpenAPI spec in this PR before submitting
    - include the process of creating an `openApi` tool with your OpenAPI spec
    - for `agent creation`, provide a user-friendly name and useful instructions customized for your API
    - for `message creation`, provide an example of a user query that can be used with your API and expected response in comments
- `OpenAPI spec` (required): the OpenAPI spec for your API
  - Your OpenAPI should be updated based on the requirements [here](https://learn.microsoft.com/en-us/azure/ai-services/agents/how-to/tools/openapi-spec?tabs=python&pivots=overview#authenticating-with-api-key) to support appropriate authentication method
  - If you require customers to update the OpenAPI spec, please provide **clear** instructions and **placeholder** on where they should update in the OpenAPI spec file and the README.file.
  - This OpenAPI spec will also be used in the Azure AI Foundry Portal user experience.
- `media` folder (optional): if you need to include any screenshots, please add the screenshots in this folder and refer to them.

## Submit your PR
Before you submit the PR, please double check:
- you have **everything** required above ready
- you have **fully** tested your code sample

Then, you can go ahead and create a PR. By creating a PR, you automatically agree to the Contributor License Agreement and see more details [here](../../../CONTRIBUTING.md). 

When creating the PR, please make sure you give your PR a reviewer-friendly name. We will come back to you within 10 business days. 

## Once your PR is approved
- customers will see a folder for the tool in `main` branch
- Azure AI Foundry Portal team will work to bring your tool to the Portal user experience.
