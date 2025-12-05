# Tripadvisor

## Description
Get travel data, guidance and reviews

## Prerequisites

* Obtain an API key for your [Tripadvisor developer account](https://www.tripadvisor.com/developers?screen=credentials).
* Make sure when you put 0.0.0.0/0 for the IP address restriction to allow traffic from Azure AI Agent Service.

## Setup
1. Go to [Azure AI Foundry portal](https://ai.azure.com/) and select your AI Project. Select **Management Center**.
   
   :::image type="content" source="../../media/tools/licensed-data/project-assets.png" alt-text="A screenshot showing the selectors for the management center for an AI project." lightbox="../../media/tools/licensed-data/project-assets.png":::

1. Select **+new connection** in the settings page.

   :::image type="content" source="./media/connected-resources.png" alt-text="A screenshot showing the connections for the selected AI project." lightbox="../../media/tools/licensed-data/connected-resources.png":::
   
1. Select **custom keys** in **other resource types**.

   :::image type="content" source="./media/custom-keys.png" alt-text="A screenshot showing the custom key option in the settings page." lightbox="../../media/tools/licensed-data/custom-keys.png":::

1. Enter the following information to create a connection to store your Tripadvisor key:
   1. Set **Custom keys** to "key", with the value being your Tripadvisor API key.
   1. Make sure **is secret** is checked.
   1. Set the connection name to your connection name. You use this connection name in your sample code or Foundry Portal later.
   1. For the **Access** setting, you can choose either *this project only* or *shared to all projects*. Just make sure in your code, the connection string of the project you entered has access to this connection.

   :::image type="content" source="./media/connect-custom-resource.png" alt-text="A screenshot showing the screen for adding Tripadvisor connection information." lightbox="../../media/tools/licensed-data/connect-custom-resource.png":::

## Use Tripadvisor tool through Foundry portal

1. To use the Tripadvisor tool in the Azure AI Foundry, in the **Create and debug** screen for your agent, scroll down the **Setup** pane on the right to **action**. Then select **Add**.

1. Select **Tripadvisor** and follow the prompts to add the tool. 

1. Give a name for your Tripadvisor tool and provide an optional description.
 
    :::image type="content" source="./media/add-data-source.png" alt-text="A screenshot showing the Tripadvisor data source." lightbox="../../media/tools/licensed-data/add-data-source.png":::

1. Select the custom key connection you just created. 

    :::image type="content" source="./media/add-connection.png" alt-text="A screenshot showing the connection for your Tripadvisor tool, and a JSON example." lightbox="../../media/tools/licensed-data/add-connection.png":::

1. Finish and start chatting.

## Connect Tripadvisor through code-first experience

You can follow the [code sample](./tripadvisor.py) to use Tripadvisor through Agent SDK.

1. Remember to store and import Tripadvisor [OpenAPI spec](./tripadvisor.json).

1. Make sure you have updated the authentication method to be `connection` and fill in the connection ID of your custom key connection.
   ``` python
   auth = OpenApiConnectionAuthDetails(security_scheme=OpenApiConnectionSecurityScheme(connection_id="your_connection_id"))
   ```
## Customer Support Contact
