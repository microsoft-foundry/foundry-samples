**IMPORTANT NOTE FROM MICROSOFT:** The sample below was created by a third party, not Microsoft, and has not been tested or verified by Microsoft. Your use is subject to the terms provided by the relevant third party.  By using the third-party sample in this file, you are acknowledging that Microsoft has no responsibility to you or others with respect to this sample.  


------

# AI News Agent

This code sample enables creating an intelligent information summarization agent designed to help executives and decision-makers stay on top of the rapidly evolving world of artificial intelligence. By continuously scanning credible news sources, it identifies and summarizes the most impactful AI developments—especially those relevant to the Microsoft ecosystem, healthcare, and legal industries.

The agent reduces information overload by prioritizing high-value updates and presenting them in a clear, digestible Markdown table format. Each summary includes a headline, date, key insight, strategic implications, and a verified source link.

**WARNING:** AI News is not a replacement for human analysis or legal due diligence. Instead, it augments executive awareness by surfacing credible developments that may require further attention or discussion. All strategic decisions and compliance assessments remain the responsibility of the end user.


## 🎯 Use Cases

1. **Daily Team Briefing:** Generate a morning digest of AI developments for Microsoft product teams.
2. **Industry Watch:** Provide Healthcare or Legal compliance teams with up-to-the-minute AI news.
3. **Executive Snapshot:** Deliver a concise AI highlights report to executives.

## 🔍 What It Does

- Searches Bing News via the BingGroundedSearchTool for the latest AI developments (last 24 hours PT)
- Filters by publication date and credible domains (e.g., gartner.com, reuters.com, wired.com, mit.edu, stanford.edu)
- Prioritizes items in this order: Microsoft+Healthcare → Microsoft+Legal → Healthcare → Legal
- Summarizes each development and outlines implications for the three focus areas
- Outputs in a Markdown table with columns: Headline, Date, Summary, Implications, Link

## 🧠 Agent Instructions

The agent follows a system prompt that enforces:
- Source filtering against a predefined list of credible domains
- Publication date constraint within the 24‑hour window
- Priority order for topic groups
- Consistent Markdown formatting for the output table

## 🛠 Tools

### BingGroundedSearchTool
- **Description:** Queries Bing News for AI-related articles
- **Auth:** Configured via `BING_SEARCH_KEY` environment variable (e.g., stored in Azure Key Vault)
- **Reference:** OpenAPI schema provided in `tools/bing-grounded-search-schema.yaml`

## 🧪 Sample Prompts

- "What are the most impactful AI developments for Microsoft in the last 24 hours?"
- "Summarize recent legal sector AI news."
- "Healthcare-related AI breakthroughs today?"

## Architecture Overview
This agent uses Azure AI Projects with the BingGroundedSearchTool to query Bing News, applies filtering and prioritization logic in Python, summarizes via Azure OpenAI, and formats output as Markdown.  
![Architecture Diagram](./assets/architecture.png)

## 📁 Example Notebook

Refer to [`demo_ai_news_usage.ipynb`](./assets/demo_ai_news_usage.ipynb) for a guided walkthrough.

## Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/your-org/azure-ai-agent-service-blueprints.git
cd azure-ai-agent-service-blueprints/ai-news
```

### 2. Provision Azure Resources with Bicep
This Bicep script will:
- Reference your existing Azure AI Agent Service project and model deployment  
- Create a Bing Grounding resource and connect it to your Cognitive Services account  
- Provision a Storage Account, App Service Plan, and Function App  

Run:
```bash
az deployment group create \
  --resource-group <rg> \
  --template-file deploy.bicep \
  --parameters functionAppName=aiNewsApp account_name=<your-cognitive-account-name>
```
- Replace `<your-cognitive-account-name>` with the name of your existing Cognitive Services account.  
- The script creates a Bing Grounding account named `bingsearch-<your-cognitive-account-name>` and a connection.

### 3. Create a `.env` file
In the project root, create `.env` containing:
```ini
PROJECT_ENDPOINT=<your-ai-agent-service-endpoint>
MODEL_DEPLOYMENT_NAME=<your-openai-model-deployment-name>
BING_CONNECTION_ID=<leave blank; Function App app setting will be injected>
```

### 4. Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Create `system_prompt.txt`
Refer to the main README for your prompt content.

### 6. Run the agent locally
```bash
python template.py
```
7. (Optional) Review and modify configuration in `template.py`.

## Configuration Guide
| Envar                   | Description                                                    |
|-------------------------|----------------------------------------------------------------|
| `PROJECT_ENDPOINT`      | Azure AI Agent Service project endpoint                        |
| `MODEL_DEPLOYMENT_NAME` | Name of the OpenAI model deployment (e.g., `gpt-4o-mini`)      |
| `BING_CONNECTION_ID`    | Resource ID of the Bing Grounding connection (injected in FUNC)|
| `USE_SAMPLE`            | Set to `true` to use local sample JSON instead of live calls   |

### Sample Data

- No input data is required; the agent runs on schedule and logs or prints the output.

### Example Agent Interaction

```text
User: What are today’s top AI developments for Microsoft and healthcare?
Agent: | Headline | Date | Summary | Implications | Link |
      |—————|———|———|——————|—|
      | ...    | ... | ...     | ...          | ...  |

User: Summarize the latest legal AI news.
Agent: | Headline | Date | Summary | Implications | Link | ... |

User: Run the AI Developments Aggregation Agent now.
Agent: (returns a Markdown table of up to 10 items)
```

### Customization Tips

- To route output to other targets (e.g., email, Teams), wrap the final table in a notification action.
- To change the timezone from Pacific, review the # Compute time window (Pacific) section and make the necessary adjustments

## Company
![Logo](./assets/marquee_insights_logo.svg)
Marquee Insights is a specialized AI consultancy delivering cutting-edge solutions. Visit [Marquee Insights](https://marqueeinsights.com).

## Support
For support, contact hello@marqueeinsights.com

## License

MIT License
