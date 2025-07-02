> [!IMPORTANT]
> Important Note From Microsoft:
> * Your use of connected non-Microsoft services is subject to the terms between you and the service provider. By connecting to a non-Microsoft service, you acknowledge that some of your data, such as prompt content, is passed to the non-Microsoft service, and/or your application might receive data from the non-Microsoft service. You are responsible for your use (and any charges associated with your use) of non-Microsoft services and data.
> * The code in this 3p-tools file were created by third parties, not Microsoft, and have not been tested or verified by Microsoft. Your use of the code samples is subject to the terms provided by the relevant third party. By using any third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to these samples.

# InsureMO Insurance Quotation

Action APIs for insurance quotations for Car, Home, and Travel.

---

This repository demonstrates how to use the InsureMO Insurance Quotation APIs (Car, Home, and Travel) with Azure AI Foundry Agent Service and OpenAPI tools. It includes a single Python sample agent that can request quotations for all supported insurance products, an OpenAPI specification, and instructions for setup and usage.

## Table of Contents

- [Overview](#overview)
- [APIs Covered](#apis-covered)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
- [Environment Variables](#environment-variables)
- [OpenAPI Specifications](#openapi-specifications)
- [Sample Agent Script](#sample-agent-script)
- [How to Run the Sample](#how-to-run-the-sample)
- [Authentication](#authentication)
- [Best Practices](#best-practices)
- [References](#references)

---

## Overview

This project provides sample code and OpenAPI specifications for integrating with InsureMO's insurance quotation APIs. The sample shows how to use Azure AI Foundry Agent Service to interact with these APIs using secure API key authentication. All three insurance products (Car, Home, and Travel) are supported in a single script, with the user input determining which quotation is requested.

---

## APIs Covered

- **Car Insurance Quotation API**: Obtain car insurance quotes.
- **Home Insurance Quotation API**: Obtain home insurance quotes.
- **Travel Insurance Quotation API**: Obtain travel insurance quotes.

All APIs are hosted on Azure Container Apps and require an API key for authentication.
To obtain API key, please contact ms@insuremo.com.

---

## Project Structure

```
insureMO_Quotation.py            # Unified Python sample for all insurance quotations
insuremo_openapi_spec.json       # OpenAPI spec for all products
.env                             # Environment variables (template)
README.md                        # Project documentation
```

---

## Prerequisites

- Python 3.8+
- Azure Subscription
- Access to Azure AI Projects (Foundry)
- InsureMO API Key and connection setup in Azure
- Required Python packages:
  - `azure-ai-projects`
  - `azure-ai-agents`
  - `azure-identity`
  - `jsonref`
  - `python-dotenv` (for `.env` support)

Install dependencies:

```bash
pip install azure-ai-projects azure-ai-agents azure-identity jsonref python-dotenv
```

---

## Setup Instructions

1. **Clone the repository** and navigate to the project directory.

2. **Set up Azure AI Project and OpenAPI Connection**:
   - Follow the instructions at [Foundry Agent Service OpenAPI Tool Authentication](https://learn.microsoft.com/en-us/azure/ai-services/agents/how-to/tools/openapi-spec?tabs=python&pivots=overview#authenticating-with-api-key) to create a custom key (with name 'X-API-KEY') connection for the InsureMO APIs.
   - Note your connection name.

3. **Configure Environment Variables**:
   - Copy `.env` and fill in your values:
     ```
     PROJECT_ENDPOINT={your_project_endpoint}
     MODEL={your_model_deployment_name}
     CONNECTION_ID={your_openapi_connection_id}
     ```
   - You can use [python-dotenv](https://pypi.org/project/python-dotenv/) to load these automatically.

4. **Ensure the OpenAPI spec file** (`insuremo_openapi_spec.json`) is present in the root directory.

---

## Environment Variables

- `PROJECT_ENDPOINT`: The Azure AI Agents endpoint.
- `MODEL`: The deployment name of the AI model to use with the agent.
- `CONNECTION_ID`: The connection ID for the OpenAPI tool.

---

## OpenAPI Specifications

- The OpenAPI spec (`insuremo_openapi_spec.json`) covers all three insurance products.
- **You can also obtain the latest OpenAPI specifications using the following publicly available GET API:**
  - [Openapi Spec](https://insuremo-insurance-tools.graysand-b1976283.westus2.azurecontainerapps.io/v1/openapi/full)

---

## Sample Agent Script

The single script `insureMO_Quotation.py` demonstrates:

- Loading the OpenAPI spec
- Authenticating with Azure AI Projects and the InsureMO API key
- Creating an agent with the OpenAPI tool
- Sending a sample user request for a quotation (car, home, or travel)
- Printing the response and cleaning up the agent

To request a different type of insurance quotation, modify the `user_input_*` variable in the script and set it as the `content` for the user message.

---

## How to Run the Sample

1. Ensure your `.env` file is configured and dependencies are installed.
2. Run the sample script:

```bash
python insureMO_Quotation.py
```

- The script will authenticate with Azure and InsureMO, create an agent and thread, send a sample insurance quotation request (car, home, or travel), print the response, and clean up the agent.
- To switch between car, home, or travel insurance, change the `content` argument in the user message section of the script to use the appropriate `user_input_car`, `user_input_home`, or `user_input_travel` variable.

---

## Best Practices

- Store secrets and connection strings securely (never hard-code in source files).
- Use environment variables and Azure Key Vault for sensitive data.
- Follow Azure's [API security best practices](https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design).
- Use the provided OpenAPI specs to validate request/response payloads.
- Clean up agents and threads after use to avoid resource leaks.

---

## References

- [InsureMO Documentation](https://www.insuremo.com/)
- [Azure AI Agents Documentation](https://learn.microsoft.com/en-us/azure/ai-services/agents/)
- [Azure OpenAPI Tool](https://learn.microsoft.com/en-us/azure/ai-services/agents/how-to/tools/openapi-spec)
- [OpenAPI Specification](https://swagger.io/specification/)
- [Customer Support email](mailto:ms@insuremo.com)

---
