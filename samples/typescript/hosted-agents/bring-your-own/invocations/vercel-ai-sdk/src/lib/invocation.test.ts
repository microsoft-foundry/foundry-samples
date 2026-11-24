import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parseInvocation } from "./invocation";
import { calculateQuote } from "./quote";

describe("parseInvocation", () => {
  it("accepts a simple message for the hosted-agent CLI", () => {
    const result = parseInvocation({ input: "Hello" });

    assert.equal(result.success, true);
    if (result.success) {
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
      assert.deepEqual(
        result.messages.map((message) => message.role),
        ["user", "user"],
      );
    }
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
