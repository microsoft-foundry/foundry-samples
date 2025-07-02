# 📊 Sales Analyst Agent

This code sample enables creating an agent that analyzes sales data. It empowers business analysts and sales teams to generate actionable insights from internal sales data, using conversational AI to simplify reporting, aggregation, and trend analysis.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

---

## 💼 Use Cases

- **Sales Report Automation**: Summarize KPIs and revenue metrics from uploaded sales files.
- **Region-wise Performance Analysis**: Identify top-performing territories by revenue, margin, or units sold.
- **Trend Breakdown & Forecasting**: Analyze historical data and forecast upcoming quarter performance using built-in analytics tools.
- **File-driven Q&A**: Ask natural language questions about Excel sales files, and receive grounded, contextual answers.

---

## 🧩 Tools

This agent is powered by **Azure AI Agent Service**, and integrates the following tools:

- **File Search**: To extract and reference structured data from uploaded sales spreadsheets.
- **Code Interpreter**: To perform on-the-fly calculations, summaries, and scenario modeling based on user input.

The agent can be customized via `template.py` and deployed with Azure infrastructure-as-code (e.g., Bicep or ARM).

---

## Setup Instructions

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


---

## 💬 Example Agent Interactions

**User**: What were the total sales in Q4 2024 across the Pacific Northwest?  
**🔍 Agent Response**: File Search pulls data rows for Q4 2024 and region = Pacific Northwest; Code Interpreter sums total sales.

---

**User**: Can you compare average order value by region for last year?  
**🔧 Agent Response**: Code Interpreter calculates and visualizes average order value per region.

---

**User**: I just uploaded a new CSV file—can you check if there’s a drop in sales in Q1 2025 compared to Q4 2024?  
**🔍 Agent Response**: File Search locates relevant time periods, Code Interpreter computes and compares sales metrics.

---

**User**: Generate a quick summary of our revenue by product category for the last 6 months.  
**🔧 Agent Response**: Code Interpreter generates a table and pie chart based on filtered data.

---

## 🛠 Customization Tips

- **Connect to Live Data Sources**  
  Extend with connectors to Azure SQL, Power BI datasets, or Dynamics 365 for real-time reporting.

- **Enrich with Metadata Tags**  
  Pre-process uploaded files with tags (e.g., region, channel, product line) to improve retrieval accuracy.

- **Forecast with External Signals**  
  Integrate a market trends tool or embed economic indicators to improve forecasting reliability.

- **Add Executive Dashboard Mode**  
  Change the `system_message` to generate polished summaries suitable for leadership review.

- **Support for Multi-file Comparison**  
  Modify the tool logic to handle cross-file comparisons for multi-quarter or multi-region datasets.

---

