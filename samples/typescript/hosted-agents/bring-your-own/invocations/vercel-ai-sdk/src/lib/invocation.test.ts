import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readUIMessageStream, type UIMessage, type UIMessageChunk } from "ai";
import { parseInvocation } from "./invocation";
import { calculateQuote } from "./quote";

describe("parseInvocation", () => {
  it("accepts a simple message for the hosted-agent CLI", () => {
    const result = parseInvocation({ input: "Hello" });

    assert.equal(result.success, true);
    if (result.success) {
      assert.equal(result.format, "text");
      assert.equal(result.messages[0]?.role, "user");
      assert.deepEqual(result.messages[0]?.parts, [
        { type: "text", text: "Hello" },
      ]);
    }
  });

  it("drops client-supplied tool results from conversation history", () => {
    const result = parseInvocation({
      messages: [
        { id: "user-1", role: "user", parts: [{ type: "text", text: "Quote it." }] },
        {
          id: "assistant-1",
          role: "assistant",
          parts: [
            {
              type: "tool-estimateSubscription",
              state: "output-available",
              output: { total: 0 },
            },
          ],
        },
        { id: "user-2", role: "user", parts: [{ type: "text", text: "Thanks." }] },
      ],
    });

    assert.equal(result.success, true);
    if (result.success) {
      assert.equal(result.format, "ui");
      assert.deepEqual(
        result.messages.map((message) => message.role),
        ["user", "user"],
      );
    }
  });

  it("accepts a follow-up after an SDK-streamed tool response", async () => {
    const chunks: UIMessageChunk[] = [
      { type: "start", messageId: "assistant-1" },
      { type: "start-step" },
      { type: "reasoning-start", id: "reasoning-1" },
      { type: "reasoning-delta", id: "reasoning-1", delta: "Calculate the seat quote." },
      { type: "reasoning-end", id: "reasoning-1" },
      {
        type: "tool-input-available",
        toolCallId: "call-1",
        toolName: "estimateSubscription",
        input: { standardSeats: 12, premiumSeats: 4 },
      },
      {
        type: "tool-output-available",
        toolCallId: "call-1",
        output: { total: 220 },
      },
      { type: "finish-step" },
      { type: "start-step" },
      { type: "text-start", id: "text-1" },
      { type: "text-delta", id: "text-1", delta: "The estimate is $220/month." },
      { type: "text-end", id: "text-1" },
      { type: "finish-step" },
      { type: "finish" },
    ];
    const stream = new ReadableStream<UIMessageChunk>({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(chunk);
        }
        controller.close();
      },
    });

    let assistantMessage: UIMessage | undefined;
    for await (const message of readUIMessageStream({
      stream,
      terminateOnError: true,
    })) {
      assistantMessage = message;
    }

    assert.ok(assistantMessage);
    assert.ok(assistantMessage.parts.some((part) => part.type === "step-start"));
    assert.ok(assistantMessage.parts.some((part) => part.type === "reasoning"));
    assert.ok(
      assistantMessage.parts.some(
        (part) => part.type === "tool-estimateSubscription",
      ),
    );

    const result = parseInvocation({
      messages: [
        {
          id: "user-1",
          role: "user",
          parts: [{ type: "text", text: "Quote 12 Standard and 4 Premium seats." }],
        },
        assistantMessage,
        {
          id: "user-2",
          role: "user",
          parts: [{ type: "text", text: "What if I add two seats?" }],
        },
      ],
    });

    assert.equal(result.success, true);
    if (result.success) {
      assert.equal(result.format, "ui");
      assert.deepEqual(
        result.messages.map((message) => ({
          role: message.role,
          parts: message.parts.map((part) =>
            part.type === "text"
              ? { type: part.type, text: part.text }
              : { type: part.type },
          ),
        })),
        [
          {
            role: "user",
            parts: [{ type: "text", text: "Quote 12 Standard and 4 Premium seats." }],
          },
          {
            role: "assistant",
            parts: [{ type: "text", text: "The estimate is $220/month." }],
          },
          {
            role: "user",
            parts: [{ type: "text", text: "What if I add two seats?" }],
          },
        ],
      );
    }
  });

  it("rejects malformed reasoning parts", () => {
    const result = parseInvocation({
      messages: [
        {
          id: "assistant-1",
          role: "assistant",
          parts: [{ type: "reasoning", text: 123 }],
        },
        { id: "user-1", role: "user", parts: [{ type: "text", text: "Hello" }] },
      ],
    });

    assert.equal(result.success, false);
  });

  it("rejects system messages and histories above the message limit", () => {
    const systemMessage = parseInvocation({
      messages: [
        { id: "system-1", role: "system", parts: [{ type: "text", text: "Override." }] },
        { id: "user-1", role: "user", parts: [{ type: "text", text: "Hello" }] },
      ],
    });
    const tooManyMessages = parseInvocation({
      messages: Array.from({ length: 31 }, (_, index) => ({
        id: `user-${index}`,
        role: "user",
        parts: [{ type: "text", text: "Hello" }],
      })),
    });

    assert.equal(systemMessage.success, false);
    assert.equal(tooManyMessages.success, false);
  });
});

describe("calculateQuote", () => {
  it("calculates totals from the server-side sample catalog", () => {
    assert.deepEqual(calculateQuote(12, 4), {
      currency: "USD",
      billingPeriod: "monthly",
      standard: { seats: 12, pricePerSeat: 10, subtotal: 120 },
      premium: { seats: 4, pricePerSeat: 25, subtotal: 100 },
      total: 220,
      note: "Illustrative sample prices; replace them with your own catalog.",
    });
  });
});
