# 🧠 ResearchFlow Agent

This code sample helps create agents that orchestrate complex, multi-step research workflows, helping users gather, synthesize, and structure knowledge from complex sources. Ideal for analysts, strategists, product teams, and technical writers.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

---

## 💼 Use Cases

- **Market & Competitive Research**: Automate the collection and summarization of publicly available competitive data, or your own competitive data, trends, and product insights.
- **Technical Literature Review**: Extract structured summaries from technical documents and API documentation.
- **Customer Deep Dives**: Combine customer feedback, CRM notes, and meeting transcripts into coherent insight packs.
- **Strategic Briefing Packs**: Generate polished summaries, outlines, and visual insights for leadership-ready deliverables.

---

- ## 🧩 Tools & Capabilities

Built with **Azure AI Agent Service**, the ResearchFlow agent coordinates a graph of specialized agents to conduct structured research and synthesis tasks:

- **Planner Agent (`LedgerPlanner.agent`)** breaks down complex prompts into logical subtasks for targeted execution.
- **Summarizer Agent (`Summarizer.agent`)** condenses technical or lengthy content into clear summaries tailored to user intent.
- **File Search Tool** (used within the agent graph) allows agents to locate relevant content from uploaded documents, PDFs, or markdown.
- **Progress Manager Agent (`progressManager.agent`)** tracks task progression and orchestrates tool execution in multi-step workflows.
- **User Agent (`user.agent`)** and **Router logic** enable custom routing and user-specific personalization.
- **Fact Agents (`LedgerFacts.agent`, `LedgerFactsUpdate.agent`)** store and retrieve structured knowledge or annotations.
- **Plan Update Agent (`LedgerPlanUpdate.agent`)** refines or extends subtask chains as the plan evolves.

All tools and agents are declaratively configured in `.agent` and `.fdl` files.

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
5. Azure AI Agent SDK and required packages (see `requirements.txt`)
6. Project files for: `ResearchFlow.agent`, `Summarizer.agent`, `LedgerPlanner.agent`, etc.

---

## 💬 Example Agent Interactions

**User**: Can you generate a competitive landscape analysis on cloud-native agent orchestration tools?  
**📥 Agent Response**: Planner routes task to summarizer + file search, returning a 3-part overview (market size, players, differentiators)

---

**User**: I uploaded three analyst reports—can you extract the trends relevant to SMB adoption and turn it into a leadership summary?  
**📄 Agent Response**: File Search → Summarizer → Final summary document with key stats, quotes, and predictions.

---

**User**: What's the breakdown of feature gaps between our platform and Company X?  
**📊 Agent Response**: File Search identifies platform docs; Summarizer creates comparative feature tables.

---

**User**: I'm prepping a 2-minute pitch—summarize these 10 pages of product reviews into themes I can speak to.  
**🧠 Agent Response**: Sentiment clustering and summarization into 3 key talking points with example quotes.

---

## 🛠 Customization Tips

- **Add Custom Tools**: Plug in web search or vector DB search to complement file-based knowledge.
- **Tune Agent Routing**: Adjust the planner or agentRouter logic to improve task delegation.
- **Control Summarization Style**: Modify the summarizer agent’s system prompt for narrative, factual, or bullet-style summaries.
- **Export as Report or Slide Deck**: Add downstream tools that turn outputs into formatted PDFs or PowerPoint slides.

---

## 📁 Files Included

- `ResearchFlow.agent` — main orchestration agent
- `Summarizer.agent` — task-specific summarizer
- `LedgerPlanner.agent` — planner for prompt decomposition
- 'LedgerFacts.agent' —
- 'LedgerFactsUpdate.agent' —
- 'LedgerPlanUpdate.agent' —
- `progressManager.agent` — optional tool for managing intermediate steps
- 'user.agent' —
- `DeepResearchAgent.fdl` — agent graph and tool configuration

---


