> [!IMPORTANT]
> Important Note From Microsoft:
> * Your use of connected non-Microsoft services is subject to the terms between you and the service provider. By connecting to a non-Microsoft service, you acknowledge that some of your data, such as prompt content, is passed to the non-Microsoft service, and/or your application might receive data from the non-Microsoft service. You are responsible for your use (and any charges associated with your use) of non-Microsoft services and data.
> * The code in this 3p-tools file were created by third parties, not Microsoft, and have not been tested or verified by Microsoft. Your use of the code samples is subject to the terms provided by the relevant third party. By using any third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to these samples.

## Auquan

**Tool Description:**
AI-powered workflow automation for institutional finance. 
The Auquan Risk Agent is an expert system designed to provide comprehensive risk analysis and timeline tracking for companies. It specializes in analyzing company risks across multiple dimensions including operational, financial, regulatory, and sustainability metrics. The tool processes structured risk data from Auquan's API, generates detailed timelines, and provides actionable insights through well-formatted json responses.

**Prerequisites**
Obtain an API key for your Auquan Risk Agent by contacting us.
You can contact us via this page : https://www.auquan.com/cta


**Setup**
1. Go to Azure AI Foundry portal and select your AI Project. Select Management Center.
2. Select +new connection in the settings page.
3. Select custom keys in other resource types.
4. Enter the following information to create a connection to store your AuquanRiskAnalyzer key:
5. Set Custom keys to "x-api-key", with the value being your AuquanRiskAnalyzer API key.
6. Make sure is secret is checked.
7. Set the connection name to your connection name. You use this connection name in your sample code or Foundry Portal later.
8. For the Access setting, you can choose either this project only or shared to all projects. Just make sure in your code, the connection string of the project you entered has access to this connection.

**Sample Queries**

- "Do a risk analysis for Darktrace"
- "What are the critical risks identified for Openai"
- "Generate a sustainability analysis for ClimatePartner"
- "What is the overall risk range of Zoom?"
- "What are the recent themes around Coursera and what are their impacts?"
- "What are the recent risks for Autodesk ?"

**Note** 
If you encounter a "rate limit exceeded" error, navigate to the "Models + Endpoints" tab in the Foundry Portal and increase the TPM (tokens per minute) limit for your model. We recommend setting it to around 100,000 to start with.


**Customer Support Contact**
support@auquan.com
