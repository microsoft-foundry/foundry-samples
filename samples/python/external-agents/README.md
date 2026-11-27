# External agent samples

An **external agent** runs outside Foundry: on your own infrastructure, in any
framework. It sends OpenTelemetry traces to the Application Insights resource
connected to your Foundry project. After you register the agent in Foundry, you
can use those traces to observe, evaluate, and improve it, without moving or
rebuilding the agent.

## Which sample should I use?

| I want to… | Sample |
|---|---|
| See the full improvement loop: find a problem in production, review it, build tests, fix, and compare | [trip-planner](trip-planner/) |
| Use Microsoft Agent Framework | [trip-planner](trip-planner/) |
| Use LangChain | [observability](observability/) |
| Connect an agent and see its traces in Foundry | Either. [observability](observability/) steps 1–4 cover it in the most detail. |
| Run a trace evaluation (single-turn or multi-turn) from code | [observability](observability/) steps 5–6 |
| Evaluate production traces continuously | [observability](observability/) step 7 |
| Find recurring issues with Agent Insights from code | [observability](observability/) step 8 |
| Generate a dataset or a rubric evaluator from traces | [observability](observability/) step 9 |

**How they differ:** `observability` is the API reference. It has one script
per capability, using a simple weather agent that works correctly.
`trip-planner` is the scenario. Its launch version has two problems on purpose,
so you can find them with Foundry, fix them, and check the fix.

## Bring your own agent

The samples use demo agents. To connect your own agent:

1. **Send traces to Application Insights.** Use the Application Insights
   resource connected to your Foundry project, for example with the
   [Microsoft OpenTelemetry distro](https://pypi.org/project/microsoft-opentelemetry/)
   (`use_microsoft_opentelemetry(enable_azure_monitor=True, ...)`).
2. **Set `gen_ai.agent.id` on the `invoke_agent` span.** Pick a stable ID; you
   register the agent with the same one. How depends on your framework:
   - Microsoft Agent Framework: `Agent(..., id="my-agent")`. See
     [trip-planner/agent.py](trip-planner/agent.py).
   - LangChain or LangGraph: pass `agent_id` in the distro's `langchain`
     instrumentation options. See
     [observability/weather_agent.py](observability/weather_agent.py).
   - Other frameworks: emit spans that follow the
     [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai),
     with `gen_ai.operation.name = invoke_agent` and `gen_ai.agent.id`.
3. **Decide on message content.** Evaluators that score what the agent said
   need prompts and responses in the traces (for example,
   `enable_sensitive_data=True`). Before you turn it on in production, decide
   what you can capture, who can see it, and how long you keep it.
4. **Check the traces.** In Application Insights, confirm the `invoke_agent`
   spans carry your `gen_ai.agent.id`.
5. **Register the agent** with that ID:
   `project.agents.create_version(agent_name="my-agent", definition=ExternalAgentDefinition(otel_agent_id="my-agent"))`,
   or in the portal under **Build** > **Agents** > **New agent** > **Link external agent**.

Then pick the capabilities you need from the samples. Each trip-planner step
lists the Contoso-specific values to replace, such as the agent's job
description and policy text.

## What you need for each capability

| Capability | Status | Model | Roles (in addition to Foundry User on the project) |
|---|---|---|---|
| Register and view traces | GA | — | You: Monitoring Reader on Application Insights |
| Trace evaluations, continuous evaluation | GA | A judge model deployment | Project managed identity: Log Analytics Reader and Privileged Monitoring Data Reader on Application Insights |
| Agent Insights | GA | GPT-5 or later | Same as trace evaluations |
| Dataset and rubric generation from traces | GA | GPT-5 or later recommended | Same as trace evaluations; [supported regions](https://learn.microsoft.com/azure/foundry/concepts/evaluation-regions-limits-virtual-network) |
| Annotations, task-level rubrics, custom evaluators, intelligent sampling, skill optimization | Preview | GPT-5 or later for skill optimization | Same as trace evaluations |

Run `az login` before the scripts; they use your Azure CLI sign-in. Role
assignments can take several minutes to apply.

## Prerequisites

Both samples need:

- A Foundry project with an Application Insights resource connected.
- An agent that emits OpenTelemetry traces following the GenAI semantic
  conventions, with a `gen_ai.agent.id` attribute on its `invoke_agent` span.
- `azure-ai-projects` 2.11.0 or later. External agents are generally available
  in that version, so no preview opt-in is needed.

## Learn more

- [Register external agents for observability and evaluation](https://learn.microsoft.com/azure/foundry/agents/how-to/register-external-agent)
