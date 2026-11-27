import {
  convertToModelMessages,
  stepCountIs,
  streamText,
  tool,
} from "ai";
import { z } from "zod";
import { maxInvocationBodyBytes, parseInvocation } from "@/lib/invocation";
import { getFoundryModel } from "@/lib/foundry-model";
import { calculateQuote } from "@/lib/quote";

export const runtime = "nodejs";

const systemPrompt =
  "You are a SaaS seat-planning assistant helping IT administrators estimate monthly license spend for growing teams. Use the estimateSubscription tool for every quote, ask for Standard and Premium seat counts when they are missing, and explain that the sample rates are illustrative rather than real vendor pricing.";

async function readBoundedBody(request: Request) {
  const reader = request.body?.getReader();
  if (!reader) {
    return { success: false as const, status: 400, error: "A request body is required." };
  }

  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    totalBytes += value.byteLength;
    if (totalBytes > maxInvocationBodyBytes) {
      await reader.cancel();
      return {
        success: false as const,
        status: 413,
        error: "The request body exceeds the 64 KiB limit.",
      };
    }
    chunks.push(value);
  }

  return {
    success: true as const,
    text: Buffer.concat(chunks).toString("utf8"),
  };
}

export async function POST(request: Request) {
  const body = await readBoundedBody(request);
  if (!body.success) {
    return Response.json({ error: body.error }, { status: body.status });
  }

  let input: unknown;
  if (request.headers.get("content-type")?.includes("application/json")) {
    try {
      input = JSON.parse(body.text) as unknown;
    } catch {
      return Response.json(
        { error: "The request body must be valid JSON." },
        { status: 400 },
      );
    }
  } else {
    input = body.text;
  }

  const invocation = parseInvocation(input);
  if (!invocation.success) {
    return Response.json({ error: invocation.error }, { status: 400 });
  }

  const result = streamText({
    model: getFoundryModel(),
    system: systemPrompt,
    messages: await convertToModelMessages(invocation.messages),
    tools: {
      estimateSubscription: tool({
        description:
          "Calculate an illustrative monthly SaaS license quote for Standard and Premium seats using the sample catalog.",
        inputSchema: z.object({
          standardSeats: z.number().int().min(0).max(1000),
          premiumSeats: z.number().int().min(0).max(1000),
        }),
        execute: async ({ standardSeats, premiumSeats }) =>
          calculateQuote(standardSeats, premiumSeats),
      }),
    },
    stopWhen: stepCountIs(3),
  });

  if (invocation.format === "ui") {
    return result.toUIMessageStreamResponse();
  }

  return result.toTextStreamResponse();
}
