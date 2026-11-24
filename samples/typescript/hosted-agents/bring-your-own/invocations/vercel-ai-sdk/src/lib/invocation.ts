import { randomUUID } from "node:crypto";
import type { UIMessage } from "ai";
import { z } from "zod";

export const maxInvocationBodyBytes = 64 * 1024;
const maxMessageCharacters = 8_000;
const maxConversationCharacters = 24_000;

const textPartSchema = z
  .object({
    type: z.literal("text"),
    text: z.string().max(maxMessageCharacters),
  })
  .passthrough();

const toolPartSchema = z
  .object({
    type: z.string().regex(/^tool-[\w-]+$/),
  })
  .passthrough();

const messagePartSchema = z.union([textPartSchema, toolPartSchema]);

const chatRequestSchema = z
  .object({
    messages: z
      .array(
        z
          .object({
            id: z.string().min(1).max(128),
            role: z.enum(["user", "assistant"]),
            parts: z.array(messagePartSchema).min(1).max(32),
          })
          .passthrough(),
      )
      .min(1)
      .max(30),
  })
  .passthrough()
  .superRefine(({ messages }, context) => {
    if (messages.at(-1)?.role !== "user") {
      context.addIssue({
        code: "custom",
        message: "The last message must be from the user.",
      });
    }

    const totalCharacters = messages.reduce(
      (messageTotal, message) =>
        messageTotal +
        message.parts.reduce(
          (partTotal, part) =>
            partTotal +
            (part.type === "text" && typeof part.text === "string"
              ? part.text.length
              : 0),
          0,
        ),
      0,
    );
    if (totalCharacters > maxConversationCharacters) {
      context.addIssue({
        code: "custom",
        message: "The conversation exceeds the supported size.",
      });
    }

    if (
      !messages.some(
        (message) =>
          message.role === "user" &&
          message.parts.some((part) => part.type === "text"),
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "At least one user text message is required.",
      });
    }
  });

const simpleMessageSchema = z
  .object({
    message: z.string().trim().min(1).max(maxMessageCharacters).optional(),
    input: z.string().trim().min(1).max(maxMessageCharacters).optional(),
  })
  .passthrough()
  .refine(({ message, input }) => Boolean(message || input));

export type ParsedInvocation =
  | { success: true; messages: UIMessage[] }
  | { success: false; error: string };

function isTextPart(
  part: z.infer<typeof messagePartSchema>,
): part is z.infer<typeof textPartSchema> {
  return part.type === "text";
}

function singleUserMessage(text: string): UIMessage[] {
  return [
    {
      id: randomUUID(),
      role: "user",
      parts: [{ type: "text", text }],
    },
  ];
}

export function parseInvocation(value: unknown): ParsedInvocation {
  if (typeof value === "string") {
    const parsedText = z
      .string()
      .trim()
      .min(1)
      .max(maxMessageCharacters)
      .safeParse(value);
    return parsedText.success
      ? { success: true, messages: singleUserMessage(parsedText.data) }
      : { success: false, error: "Provide a non-empty message of at most 8000 characters." };
  }

  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { success: false, error: "The invocation body must be an object or text." };
  }

  if ("messages" in value) {
    const parsed = chatRequestSchema.safeParse(value);
    if (!parsed.success) {
      return { success: false, error: "The chat history is invalid or too large." };
    }

    const messages: UIMessage[] = parsed.data.messages
      .map((message) => ({
        id: message.id,
        role: message.role,
        parts: message.parts.filter(isTextPart),
      }))
      .filter((message) => message.parts.length > 0);

    return { success: true, messages };
  }

  const parsed = simpleMessageSchema.safeParse(value);
  if (!parsed.success) {
    return { success: false, error: 'Provide a "message" or "input" string.' };
  }

  const text = parsed.data.message ?? parsed.data.input;
  return text
    ? { success: true, messages: singleUserMessage(text) }
    : { success: false, error: 'Provide a "message" or "input" string.' };
}
