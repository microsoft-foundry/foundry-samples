# 🧠 MagenticOne Agent

This code sample showcases a generalist, autonomous multi-agent system that helps create an agent to perform deep research and problem-solving by orchestrating web search, code generation, and code execution agents. Helpful for tackling open-ended analytical or technical tasks.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

---

## 💼 Use Cases

- **Multi-Source Reasoning**: Pull together content from search engines, websites, and structured files to form a grounded response.
- **Technical Problem Solving**: Execute and validate small-scale Python code to solve algorithmic or data wrangling tasks.
- **Complex Web Queries**: Navigate unstructured questions by orchestrating real-time web search and document parsing.
- **Agent Demos or Debugging**: Use as a scaffold to test autonomous planning and coordination in agent graphs.

---

## 🧩 Tools & Capabilities

Built with **Azure AI Agent Service**, the MagenticOne agent graph includes:

- **Planner Agent (`magneticOneCode.agent`)** to break down the user’s high-level task into smaller, tractable goals.
- **WebBrowse Agent** to simulate multi-turn browsing and interaction with live websites.
- **BingSearch Agent** to retrieve recent or factual content with citation grounding.
- **CodeExecutor Agent** to perform lightweight computation, validation, or summarization of structured data.


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
   
- Azure AI Agent SDK and dependencies (`requirements.txt`)
- Agent files: `magneticOneCode.agent`, `webBrowse.agent`, `codeExecutor.agent`, `BingSearch.agent`
- Orchestration graph: `magentic.one.fdl`

---

## 💬 Example Agent Interactions

**User**: Can you find the latest benchmarks for GPT-4 on reasoning tasks and compare them to Claude 3?  
**🌐 Agent Response**: BingSearch gathers content → WebBrowse validates source → Summarizer produces side-by-side results

---

**User**: What’s the Python code to calculate BLEU score from two text files?  
**💻 Agent Response**: Planner routes to CodeExecutor with import and scoring logic

---

**User**: Read the OpenAI DevDay transcript and summarize new agent features by category.  
**📖 Agent Response**: WebBrowse extracts the transcript → CodeExecutor categorizes → Final structured output delivered

---

**User**: Which generative AI tools support document-level RAG and schema control?  
**🔎 Agent Response**: Planner routes task to BingSearch → WebBrowse extracts pros/cons → Summary grounded in retrieved URLs

---

## 🛠 Customization Tips

- **Replace BingSearch with FileSearch**: To handle documents uploaded to your Azure AI Project.
- **Extend Code Execution**: Add guards or more libraries to run evals, format charts, or parse JSON.
- **Test Autonomous Mode**: Run planner + tools with minimal user prompting for an agent demo.
- **Adapt for Voice Agents**: Combine with Voice Live Agent to make this a spoken assistant for devs or analysts.

---

## 📁 Files Included

- `magneticOneCode.agent` — primary planner agent
- `webBrowse.agent` — browser simulation for agent exploration
- `BingSearch.agent` — fetches grounded real-time results
- `codeExecutor.agent` — evaluates and returns Python logic or math
