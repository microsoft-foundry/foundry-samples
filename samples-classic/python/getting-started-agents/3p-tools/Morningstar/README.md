> [!IMPORTANT]
> Important Note From Microsoft:
> * Your use of connected non-Microsoft services is subject to the terms between you and the service provider. By connecting to a non-Microsoft service, you acknowledge that some of your data, such as prompt content, is passed to the non-Microsoft service, and/or your application might receive data from the non-Microsoft service. You are responsible for your use (and any charges associated with your use) of non-Microsoft services and data.
> * The code in this 3p-tools file were created by third parties, not Microsoft, and have not been tested or verified by Microsoft. Your use of the code samples is subject to the terms provided by the relevant third party. By using any third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to these samples.

# Morningstar

## Description
The Morningstar tool connects your generative AI applications to Morningstar's trusted content with ease - no custom consumption pipelines required. Simply connect, query, and rely on the same continually-improving engine that powers Morningstar's in-product generative AI capabilities. Access up-to-date investment research and data such as analyst research, expert commentary, and essential Morningstar data.

## Prerequisites

* Create a Morningstar account, if you don't already have one.
    For access request please email us at iep-dev@morningstar.com using the subject line:
    Subject: Morningstar Agent Access Request
    In the body of the email, include the following:
    1. Your full name
    2. Contact information
    3. A brief description of your request and how you intend to use the Morningstar Agent.
* To fetch your JWT token, you can refer to this page: https://developer.morningstar.com/direct-web-services/documentation/documentation/get-started/authorization-tokens
    Note: Tokens are valid for 60 minutes and can be reused as many times as necessary during that time. To refresh the token, send a new request.


## Setup
1. Go to [Azure AI Foundry portal](https://ai.azure.com/) and select your AI Project. Select **Management Center**.
   
   :::image type="content" source="./media/project-assets.png" alt-text="A screenshot showing the selectors for the management center for an AI project." lightbox="./media/project-assets.png":::

2. Select **+new connection** in the settings page.

   :::image type="content" source="./media/connected-resources.png" alt-text="A screenshot showing the connections for the selected AI project." lightbox="./media/connected-resources.png":::
   
3. Select **custom keys** in **other resource types**.

   :::image type="content" source="./media/custom-keys.png" alt-text="A screenshot showing the custom key option in the settings page." lightbox="./media/custom-keys.png":::

4. Enter the following information to create a connection to store your Morningstar authorization:
   1. Set **Custom keys** to "authorization", with the value being "Bearer {JWT token}".
   2. Make sure **is secret** is checked.
   3. Set the connection name to your connection name. You use this connection name in your sample code or Foundry Portal later.
   4. For the **Access** setting, you can choose either *this project only* or *shared to all projects*. Just make sure in your code, the connection string of the project you entered has access to this connection.

   :::image type="content" source="./media/connect-custom-resource.png" alt-text="A screenshot showing the screen for adding Morningstar connection information." lightbox="./media/connect-custom-resource.png":::

## Use Morningstar tool through Foundry portal

1. To use the Morningstar tool in the Azure AI Foundry, in the **Create and debug** screen for your agent, scroll down the **Setup** pane on the right to **knowledge**. Then select **Add**.
2. Select **Morningstar** and follow the prompts to add the tool. 
3. Give a name for your Morningstar tool and provide an optional description.
4. Select the custom key connection you just created. 
5. Finish and start chatting.

## Connect Morningstar through code-first experience

You can follow the [code sample](./morningstar.py) to use Morningstar through Agent SDK.

1. Remember to store and import Morningstar [OpenAPI spec](./morningstar.json).

2. Make sure you have updated the authentication method to be `connection` and fill in the connection ID of your custom key connection.
   The connection-id should be in the following format: "/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.CognitiveServices/accounts/{ai_service_name}/projects/{project_name}/connections/{connection_name}"
   
   ``` python
   auth = OpenApiConnectionAuthDetails(security_scheme=OpenApiConnectionSecurityScheme(connection_id="your_connection_id"))
   ```

## Customer Support Contact
If you need support or would like to submit a request, please email us at iep-dev@morningstar.com using the subject line:
Subject: Morningstar Agent Request
 
In the body of the email, include the following:
- Your full name
- Contact information
- A brief description of your request or issue
- Any relevant attachments or screenshots
We'll get back to you as soon as possible. Thanks for reaching out!
