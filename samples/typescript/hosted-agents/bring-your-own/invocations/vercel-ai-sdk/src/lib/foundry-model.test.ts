import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { stepCountIs, streamText, tool } from "ai";
import { z } from "zod";
import { createFoundryResponsesModel } from "./foundry-model";

describe("createFoundryResponsesModel", () => {
  it("sends typed message items to Foundry Responses", async () => {
    let requestUrl: URL | undefined;
    let requestBody: Record<string, unknown> | undefined;
    const model = createFoundryResponsesModel({
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
            'data: {"type":"response.created","response":{"id":"resp_1","created_at":1,"model":"gpt-5.4-mini"}}',
            'data: {"type":"response.output_item.added","output_index":0,"item":{"type":"message","id":"msg_1"}}',
            'data: {"type":"response.output_text.delta","item_id":"msg_1","delta":"ok"}',
            'data: {"type":"response.output_item.done","output_index":0,"item":{"type":"message","id":"msg_1"}}',
            'data: {"type":"response.completed","response":{"usage":{"input_tokens":1,"output_tokens":1}}}',
            "",
          ].join("\n\n"),
          { headers: { "content-type": "text/event-stream" } },
        );
      },
    });

    const result = streamText({
      model,
      system: "Use the estimateSubscription tool for calculations.",
      messages: [
        { role: "user", content: "Estimate a subscription." },
        { role: "assistant", content: "How many seats?" },
        { role: "user", content: "12 Standard seats." },
      ],
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
    assert.equal(requestUrl?.pathname, "/api/projects/test/openai/v1/responses");
    const items = requestBody?.input as Array<{ type?: string; role?: string }>;
    assert.equal(items.length, 4);
    for (const item of items) {
      assert.equal(item.type, "message");
    }
    assert.equal(
      (requestBody?.tools as Array<{ name: string }>)[0]?.name,
      "estimateSubscription",
    );
  });
});
