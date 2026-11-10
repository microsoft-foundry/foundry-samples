import { readFile } from "node:fs/promises";
import { clientFromEnvironment } from "./agent-control.mjs";

try {
  if (process.argv.length !== 3) throw new Error("Usage: node evaluate.mjs <context.json>");
  const context = JSON.parse(await readFile(process.argv[2], "utf8"));
  const result = await clientFromEnvironment().evaluate(context);
  console.log(JSON.stringify({
    decision: result.verdict.decision,
    reason: result.verdict.reason ?? null,
    evaluationId: result.receipt.evaluationId,
  }, null, 2));
  process.exitCode = result.verdict.decision === "deny" ? 2 : 0;
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
