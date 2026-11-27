import assert from "node:assert/strict";
import { after, it } from "node:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createUIMessageStreamResponse, type UIMessageChunk } from "ai";
import { act } from "react";

const NativeResponse = globalThis.Response;
const NativeTransformStream = globalThis.TransformStream;
const NativeWritableStream = globalThis.WritableStream;

GlobalRegistrator.register({ url: "http://localhost:8088" });
// The AI SDK needs web streams rather than Happy DOM's Node stream globals.
globalThis.Response = NativeResponse;
globalThis.TransformStream = NativeTransformStream;
globalThis.WritableStream = NativeWritableStream;
Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", {
  configurable: true,
  value: true,
});

const { createRoot } = await import("react-dom/client");
const { default: Home } = await import("./page");

after(async () => {
  Reflect.deleteProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT");
  await GlobalRegistrator.unregister();
});

function enterText(input: HTMLInputElement, text: string) {
  const setValue = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  assert.ok(setValue);
  setValue.call(input, text);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

it("clears a failed conversation and starts a fresh chat", async () => {
  const originalFetch = globalThis.fetch;
  const firstRequest = Promise.withResolvers<void>();
  const firstResponse = Promise.withResolvers<Response>();
  const secondRequest = Promise.withResolvers<void>();
  const streamController = Promise.withResolvers<ReadableStreamDefaultController<UIMessageChunk>>();
  const stream = new ReadableStream<UIMessageChunk>({
    start(controller) {
      streamController.resolve(controller);
    },
  });
  const controller = await streamController.promise;
  let streamClosed = false;
  const requests: unknown[] = [];

  globalThis.fetch = async (_url, init) => {
    const body = init?.body;
    assert.ok(typeof body === "string");
    requests.push(JSON.parse(body));
    if (requests.length === 1) {
      firstRequest.resolve();
      return firstResponse.promise;
    }
    secondRequest.resolve();
    return createUIMessageStreamResponse({ stream });
  };

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  try {
    await act(async () => root.render(<Home />));
    const input = container.querySelector("input");
    const form = container.querySelector("form");
    const newChat = [...container.querySelectorAll("button")].find(
      (button) => button.textContent === "New chat",
    );
    assert.ok(input);
    assert.ok(form);
    assert.ok(newChat);

    await act(async () => enterText(input, "First quote"));
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await firstRequest.promise;
    });
    assert.equal(newChat.disabled, true);

    await act(async () => {
      firstResponse.resolve(new NativeResponse("History limit reached", { status: 400 }));
    });
    assert.match(container.textContent ?? "", /First quote/);
    assert.match(container.textContent ?? "", /History limit reached/);
    assert.equal(newChat.disabled, false);

    await act(async () => enterText(input, "Unsaved draft"));
    await act(async () => newChat.click());
    assert.equal(input.value, "");
    assert.doesNotMatch(container.textContent ?? "", /First quote|History limit reached/);

    await act(async () => enterText(input, "Fresh quote"));
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await secondRequest.promise;
    });

    const freshRequest = requests[1];
    assert.ok(freshRequest && typeof freshRequest === "object" && "messages" in freshRequest);
    assert.ok(Array.isArray(freshRequest.messages));
    assert.equal(freshRequest.messages.length, 1);
    assert.equal(freshRequest.messages[0].role, "user");
    assert.deepEqual(freshRequest.messages[0].parts, [
      { type: "text", text: "Fresh quote" },
    ]);

    await act(async () => {
      controller.enqueue({ type: "start", messageId: "assistant-1" });
      controller.enqueue({ type: "text-start", id: "text-1" });
      controller.enqueue({ type: "text-delta", id: "text-1", delta: "Calculating quote" });
    });
    assert.match(container.textContent ?? "", /Calculating quote/);
    assert.equal(newChat.disabled, true);
    await act(async () => newChat.click());
    assert.match(container.textContent ?? "", /Fresh quote/);

    await act(async () => {
      controller.enqueue({ type: "text-end", id: "text-1" });
      controller.enqueue({ type: "finish" });
      controller.close();
      streamClosed = true;
    });
    assert.equal(newChat.disabled, false);
  } finally {
    firstResponse.resolve(new NativeResponse("Test cleanup", { status: 400 }));
    if (!streamClosed) {
      controller.close();
    }
    await act(async () => root.unmount());
    container.remove();
    globalThis.fetch = originalFetch;
  }
});
