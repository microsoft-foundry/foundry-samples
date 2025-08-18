> [!IMPORTANT]
> Important Note From Microsoft:
> * Your use of connected non-Microsoft services is subject to the terms between you and the service provider. By connecting to a non-Microsoft service, you acknowledge that some of your data, such as prompt content, is passed to the non-Microsoft service, and/or your application might receive data from the non-Microsoft service. You are responsible for your use (and any charges associated with your use) of non-Microsoft services and data.
> * The code in this 3p-tools file were created by third parties, not Microsoft, and have not been tested or verified by Microsoft. Your use of the code samples is subject to the terms provided by the relevant third party. By using any third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to these samples.

# Lexis API Solutions

## Description
Seamless access to LexisNexis content

## Prerequisites
- Register at www.lexisnexis.com/legalapiportal if you do not have a LexisNexis API account
- Obtain a Client ID and Secret from LexisNexis technical contact
- To fetch your Token, you can refer to [the Authentication Step here](https://devportal.api-prod.route53.lexis.com/api?spec=MakeYourFirstRequest.yml) for creating the call. Tokens are valid for 24 hours. You can send same request to retrieve another token.

## Setup

1. Go to [Azure AI Foundry portal](https://ai.azure.com/) and select your AI Project. Select **Management Center**.

2. Select **+new connection** in the settings page.

3. Select **custom keys** in **other resource types**.

4. Enter the following information to create a connection to store your Lexis API Solutions authorization:
    1. Set **Custom keys** to "Authorization", with the value being "Bearer {JWT token}".
    2. Make sure **is secret** is checked.
    3. Set the connection name to your connection name. You use this connection name in sample code or Foundry Portal later.
    4. For the **Access** setting, you can choose either *this project only* or *shared to all projects*. Just make sure in your code, the connection string of the project you entered has access to this connection.


## Use Lexis API Solutions

1. You can follow the [code sample](./lexisnexis_api.py) to use Lexis API Solutions through Agent SDK.
1. Before running the sample:
   1. pip install azure-ai-agents azure-identity python-dotenv azure-ai-projects jsonref
   1. Set these environment variables with your own values:
   1. PROJECT_ENDPOINT - the Azure AI Foundry project endpoint.
   1. MODEL - The deployment name of the AI model, as found under the "Name" column in the "Models + endpoints" tab in your Azure AI Foundry project.
   1. LEXIS_API_CONNECTION_NAME - The name of the connection for the Lexis API. Format will be    "/subscriptions//resourceGroups//providers/Microsoft.CognitiveServices/accounts//projects//connections/"


## Customer Support Contact
Visit https://devportal.api-prod.route53.lexis.com/support.
