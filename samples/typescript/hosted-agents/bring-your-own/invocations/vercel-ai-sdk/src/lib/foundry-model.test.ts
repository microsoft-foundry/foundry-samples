import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { stepCountIs, streamText, tool } from "ai";
import { z } from "zod";
import { createFoundryChatModel } from "./foundry-model";

describe("createFoundryChatModel", () => {
  it("sends streamed tool requests through Foundry Chat Completions", async () => {
    let requestUrl: URL | undefined;
    let requestBody: Record<string, unknown> | undefined;
    const model = createFoundryChatModel({
      endpoint: "https://foundry.example/api/projects/test",
      deployment: "gpt-5.4-mini",
      apiKey: "test-token",
      fetch: async (input, init) => {
        requestUrl = new URL(
          input instanceof Request ? input.url : input.toString(),
        );
        requestBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return new Response(
          [
            'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1,"model":"gpt-5.4-mini","choices":[{"index":0,"delta":{"role":"assistant","content":"ok"},"finish_reason":null}]}',
            'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1,"model":"gpt-5.4-mini","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
            "",
          ].join("\n\n"),
          { headers: { "content-type": "text/event-stream" } },
        );
      },
    });

    const result = streamText({
      model,
      system: "Use the estimateSubscription tool for calculations.",
      messages: [{ role: "user", content: "Estimate a subscription." }],
      tools: {
        estimateSubscription: tool({
          description: "Calculate a sample subscription total.",
          inputSchema: z.object({ standardSeats: z.number().int() }),
          execute: async ({ standardSeats }) => ({ total: standardSeats * 10 }),
        }),
      },
      stopWhen: stepCountIs(1),
    });

    assert.equal(await result.text, "ok");
    assert.equal(
      requestUrl?.pathname,
      "/api/projects/test/openai/v1/chat/completions",
    );
    assert.equal(requestBody?.model, "gpt-5.4-mini");
    assert.equal(
      (requestBody?.tools as Array<{ function: { name: string } }>)[0]?.function
        .name,
      "estimateSubscription",
    );
  });
});
