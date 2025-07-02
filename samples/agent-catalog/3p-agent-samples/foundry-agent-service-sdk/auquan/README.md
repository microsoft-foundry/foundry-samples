**IMPORTANT NOTE FROM MICROSOFT:** The sample below was created by a third party, not Microsoft, and has not been tested or verified by Microsoft. Your use is subject to the terms provided by the relevant third party.  By using the third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to this sample.  


------

# Auquan Due Diligence Risk Analyst Agent

This code sample for the Due Diligence Risk Analyst enables building an expert system designed to provide comprehensive risk analysis and timeline tracking for companies. It specializes in analyzing company risks across multiple dimensions including operational, financial, regulatory, and sustainability metrics. The agent processes structured risk data from Auquan's API, generates detailed timelines, and provides actionable insights through well-formatted reports with visual risk indicators.

---

## 💼 Use Cases
1. Comprehensive Risk Analysis
2. Specific Risk Assessment
3. Sustainability Analysis
4. Risk Table Creation
5. Overall Risk Rating Analysis
6. Recent Theme Analysis

---

## 🧩 Tools

This agent leverages **Azure AI Agent Service**, using the following tools:
## Tool 1: Auquan API
**Description:** 
Retrieves and processes company risk data from Auquan's API. This tool enables the agent to access comprehensive company information, risk assessments, and thematic analysis data.

**API Endpoint:** `https://agents.auquan.com/api/analyze-query`
**Authentication:** API key in x-api-key header
**Request Format:**
```json
{
  "query": "do a risk analysis for {COMPANY_NAME}"
}
```

**Error Handling:**
- 401: Check API key validity
- 500: Retry with backoff
- Log all errors for monitoring

### Tool 2: Code Interpreter
**Description:**
Performs data analysis and visualization tasks including:
- Risk score calculations
- Timeline generation
- Data formatting and structuring
- Table and chart creation

**Reference Files:**
- No specific reference files required
- No authentication required

### Tool 3: Grounding with Bing Search
**Description:**
Enriches the analysis with:
- Latest news and developments
- Regulatory updates
- Industry trends
- Sustainability initiatives

**Reference Files:**
- No specific reference files required
- No authentication required

The agent is configured via a `template.py` file and deployable with Bicep for enterprise use.


## ⚙️ Setup Instructions

### Prerequisites
1. Azure subscription with the following permissions
   - Contributor or Cognitive Services Contributor role (for resource deployment)
   - Azure AI Developer and Cognitive Services user role (for agent creation)
2. Agent setup: deploy the latest agent setup using this ([custom deployment](https://www.aka.ms/basic-agent-deployment)).
   - The above creates:
      - AI Services resource
      - AI Project
      - Model deployment
3. Python 3.8+
4. Azure CLI
5. An API key for your Auquan Risk Agent. Please contact support@auquan.com to request an API key based on your desired usage.

---

### Steps
1. **Clone the Repository**

2. **Set Environment Variables**
```bash
PROJECT_ENDPOINT="<your-project-endpoint>" # (https://<your-ai-services-account-name>.services.ai.azure.com/api/projects/<your-project-name>)
MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
OPENAPI_CONNECTION_ID="<your-Auquantool-connection-id>"

---

3. **Deploy Resources**

4. **Run the Agent Script**
```bash
template.py
```
---
## 💬 Example Agent Interactions

- "Do a risk analysis for Darktrace"

- "What are the critical risks identified for Openai"

- "Generate a sustainability analysis for ClimatePartner"

- "What is the overall risk range of Zoom?"

- "What are the recent themes around Coursera and what are their impacts?"

- "What are the recent risks for Autodesk ?"

 
## 🛠 Customization Tips

- **Connect with more datasets**  
  Add datasets like lawsuits/sanctions to the agent's analysis via the Auquan Knowledge tool to identify potential risks.

- **Connect with vector stores**  
  Connect with vector stores that have specific data (eg. Annual Reports, Industry Reports etc.) ingested into them.

- **Connect with local files**  
  Add your local files to include your data in risk-analysis


## Note : 
If you encounter a "rate limit exceeded" error, navigate to the "Models + Endpoints" tab in the Foundry Portal and increase the TPM (tokens per minute) limit for your model. We recommend setting it to around 100,000 to start with.
