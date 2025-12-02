> [!IMPORTANT]
> Important Note From Microsoft:
> * Your use of connected non-Microsoft services is subject to the terms between you and the service provider. By connecting to a non-Microsoft service, you acknowledge that some of your data, such as prompt content, is passed to the non-Microsoft service, and/or your application might receive data from the non-Microsoft service. You are responsible for your use (and any charges associated with your use) of non-Microsoft services and data.
> * The code in this 3p-tools file were created by third parties, not Microsoft, and have not been tested or verified by Microsoft. Your use of the code samples is subject to the terms provided by the relevant third party. By using any third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to these samples.

# Trademo Shipments And Tariff

This Python script demonstrates how to use Azure AI to create an agent that queries global trade duties using an OpenAPI specification.

## About Tool:
- Name: Trademo Shipments And Tariff
- Description: Provides latest duties and past shipment data for trade between multiple countries


## Features
- Creates an Azure AI Project client
- Sets up OpenAPI connection for global trade data
- Processes trade duty queries
- Handles thread/message management

## Prerequisites
- Azure subscription
- Azure AI Projects resource
- Python 3.8+
- Azure CLI installed and logged in
- Required Python packages:
  - azure-ai-projects
  - azure-identity
  - jsonref
  - azure-ai-agents

## Installation
Install dependencies:
```bash
pip install azure-ai-projects azure-identity azure-ai-agents jsonref
```


## Usage
Run the script:
```bash
python trademo_and_tariff.py
```

Before running the sample:

Obtain the sessionid from trademo which serves as the API_KEY.

Set up a custom key connection, name the key as 'sessionid' and save the connection name.

Save that connection name as the PROJECT_OPENAPI_CONNECTION_NAME environment variable


Set this environment variables with your own values:
PROJECT_ENDPOINT - the Azure AI Project endpoint, as found in your Foundry Project.
MODEL - name of the model deployment in the project to use Agents against
CONNECTION_ID - The ID of connection(connection id should be in the format "/subscriptions/<sub-id>/resourceGroups/<your-rg-name>/providers/Microsoft.CognitiveServices/accounts/<your-ai-services-name>/projects/<your-project-name>/connections/<your-connection-name>")


## Example queries processed by the tool:
- "How many GPUs(HS code 847330) were imported to United States from China in February 2025?"
- "which were the top countries based on shipment value that exported jewellery(HS code 711319) to usa in 2024?"
- "Which countries are the biggest exporter of lithium ion battery(HS code 850760) to the US in 2024?"
- "what is the duty of import for jewllery(HS code =  711319) from India to US?"
- "Compare current duties on lithium ion batteries(HS code 850760) imported to US"

## Notes
- The script creates and deletes the agent during execution
- OpenAPI connection requires additional setup in Azure
- The agent assumes HS 6-digit codes for products automatically
- Error handling is included for failed runs


## Contact
For any queries, please follow the below escalation matrix:
- [support@trademo.com](mailto:support@trademo.com)
- [akshit.gupta@trademo.com](mailto:akshit.gupta@trademo.com)
- [devesh@trademo.com](mailto:devesh@trademo.com)
