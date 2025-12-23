# 💬 A2A Foundry Agent
Azure AI Foundry supports Google's open protocol called [Agent2Agent (A2A)](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/), enabling seamless interoperability across agents and third-party tools. This includes:

Azure AI Foundry Agent Service introduces a new A2A API head, enabling open-source orchestrators to connect with Foundry Agent Service agents without requiring custom integrations. This API head supports multi-turn conversations, seamless context handoffs, and bi-directional communication, making it easier for developers to extend their existing agent systems without rebuilding core logic.

This code sample demonstrates how Azure AI Foundry agents are A2A compatible. The sample uses the `Azure.AI.Agents.Persistent` to create a foundry agent, but then interacts with the agents via the `a2a-net.Client` SDK. It uses `Azure.Identity` for EntraID auth using the A2A client library.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this folder are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

## 🧩 Key features
- **Open A2A API Head**: Allows third-party orchestrators to invoke agents from Foundry Agent Service, facilitating task delegation and context-aware processing.
- **Multi-Turn Interactions**: Enables agents to handle multi-step conversations and pass context fluidly between agents, ensuring consistent responses.
- **Cross-Platform Flexibility**: Designed to work with a wide range of open-source agent frameworks, including AutoGen, LangChain, and Semantic Kernel, providing maximum flexibility for developers.

## Get Started

Please install the dependencies using the following command.

```bash
make restore build run
```
