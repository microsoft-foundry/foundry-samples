import { app, type InvocationContext } from "@azure/functions";

export function greet(
  _toolArguments: unknown,
  context: InvocationContext,
): string {
  return `Hello from the agent's tool. Invocation ID: ${context.invocationId}`;
}

app.mcpTool("greet", {
  toolName: "greet",
  description: "Greets the caller.",
  toolProperties: {},
  handler: greet,
});
