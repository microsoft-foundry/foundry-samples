import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";
import { AgentContextBuilder } from "@responsibleai/agent-hooks";
import { clientFromEnvironment, PolicyDenied } from "./agent-control.mjs";

export async function runDemo(client) {
  const builder = new AgentContextBuilder({
    agentId: "support-demo",
    framework: "custom",
    sessionId: randomUUID(),
  });
  let dispatched = 0;

  async function guarded(context, action = () => undefined) {
    const result = await client.guard(context, action);
    console.log(JSON.stringify({
      point: context.interception_point,
      evaluationId: result.receipt.evaluationId,
      outcome: "completed",
    }));
    return result.value;
  }

  await guarded(builder.agentStartup(["lookup_order", "refund_order"]));
  const input = await guarded(builder.input("Please check the refund policy."), (ctx) => ctx.input.content);
  const messages = await guarded(
    builder.preModelCall("simulated-model", [{ role: "user", content: input }]),
    (ctx) => ctx.messages,
  );
  assert(messages.length > 0);
  await guarded(builder.postModelCall("simulated-model", "I will check the request.", [], "stop"));

  const approved = await guarded(
    builder.preToolCall("refund-1", "refund_order", { order_id: "demo-001", amount: 100 }),
    (ctx) => {
      dispatched += 1;
      return {
        args: ctx.tool_call.args,
        result: { status: "simulated", amount: ctx.tool_call.args.amount },
      };
    },
  );
  await guarded(builder.postToolCall(
    "refund-1", "refund_order", approved.args, approved.result,
  ));

  try {
    await guarded(
      builder.preToolCall("refund-2", "refund_order", { order_id: "demo-001", amount: 100.01 }),
      () => { dispatched += 1; },
    );
    throw new Error("The over-limit refund was unexpectedly permitted");
  } catch (error) {
    if (!(error instanceof PolicyDenied)) throw error;
    console.log(JSON.stringify({
      point: "pre_tool_call",
      evaluationId: error.evaluation.receipt.evaluationId,
      outcome: "blocked",
      reason: error.evaluation.verdict.reason,
    }));
  }
  await guarded(builder.output("The demonstration is complete."), (ctx) => ctx.output.content);
  await guarded(builder.agentShutdown("completed"));
  assert.equal(dispatched, 1, "The denied tool call must never be dispatched");
  console.log("PASS: all eight points evaluated; one simulated tool call ran; the over-limit call did not.");
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    await runDemo(clientFromEnvironment());
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
