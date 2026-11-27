"use client";

import { useMemo, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";

export default function Home() {
  const [input, setInput] = useState("");
  const transport = useMemo(
    () => new DefaultChatTransport({ api: "/invocations" }),
    [],
  );
  const { messages, sendMessage, setMessages, clearError, status, error } =
    useChat({ transport });
  const isBusy = status === "submitted" || status === "streaming";

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isBusy) {
      return;
    }
    setInput("");
    sendMessage({ text });
  }

  function handleNewChat() {
    setMessages([]);
    clearError();
    setInput("");
  }

  return (
    <main>
      <h1>Vercel AI SDK + Foundry Hosted Agents</h1>
      <p className="intro">
        This local chat UI sends the complete message history to the agent.
        Plan monthly SaaS seats and see the agent calculate a quote with a
        server-side tool.
      </p>
      <section className="messages" aria-live="polite">
        {messages.map((message) => (
          <article
            className="message"
            data-role={message.role}
            key={message.id}
          >
            <strong>{message.role}</strong>
            {message.parts.map((part, index) => {
              if (part.type === "text") {
                return <p key={`${message.id}-${index}`}>{part.text}</p>;
              }
              if (part.type.startsWith("tool-")) {
                return (
                  <p key={`${message.id}-${index}`}>
                    Tool: {part.type.slice("tool-".length)}
                  </p>
                );
              }
              return null;
            })}
          </article>
        ))}
      </section>
      <form onSubmit={handleSubmit}>
        <input
          aria-label="Message"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Estimate monthly spend for 12 Standard and 4 Premium seats"
        />
        <button disabled={isBusy || !input.trim()} type="submit">
          {isBusy ? "Thinking…" : "Send"}
        </button>
        <button disabled={isBusy} onClick={handleNewChat} type="button">
          New chat
        </button>
      </form>
      {error ? <p className="error">{error.message}</p> : null}
    </main>
  );
}
