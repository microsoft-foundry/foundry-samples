// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

import "dotenv/config";
import { AIProjectClient } from "@azure/ai-projects";
import { DefaultAzureCredential } from "@azure/identity";
import { readFile, stat } from "node:fs/promises";
import { extname } from "node:path";

const maxImageBytes = 8 * 1024 * 1024;
const defaultImagePrompt = "Describe this image briefly.";
const imageMediaTypes = new Map<string, string>([
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".png", "image/png"],
  [".webp", "image/webp"],
]);

type VoiceAgentConnection = Awaited<
  ReturnType<AIProjectClient["beta"]["voiceAgents"]["realtime"]["connect"]>
>;
type VoiceAgentClientEvent = Parameters<VoiceAgentConnection["sendEvent"]>[0];
type ImageInputEvent = Extract<
  VoiceAgentClientEvent,
  { type: "conversation.item.create" }
>;

interface ImageTurnConnection {
  sendEvent(event: ImageInputEvent): Promise<void>;
  requestResponse(): Promise<void>;
}

async function imageDataUrl(path: string): Promise<string> {
  const file = await stat(path);
  validateImage(path, file.size);
  const image = await readFile(path);
  const mediaType = validateImage(path, image.byteLength);
  return `data:${mediaType};base64,${image.toString("base64")}`;
}

function validateImage(path: string, byteLength: number): string {
  const mediaType = imageMediaTypes.get(extname(path).toLowerCase());
  if (!mediaType) {
    throw new Error("Choose a JPEG, PNG, or WebP image.");
  }
  if (byteLength === 0) {
    throw new Error("The image must not be empty.");
  }
  if (byteLength > maxImageBytes) {
    throw new Error("Choose an image no larger than 8 MiB.");
  }
  return mediaType;
}

// The SDK doesn't yet expose a convenience method for image content, so this
// sample sends the generated realtime client event directly.
// <image_turn>
function buildImageEvent(dataUrl: string, prompt: string) {
  return {
    type: "conversation.item.create",
    item: {
      type: "message",
      role: "user",
      content: [
        { type: "input_text", text: prompt.trim() || defaultImagePrompt },
        {
          type: "input_image",
          image_url: dataUrl,
          detail: "low",
        },
      ],
    },
  } satisfies ImageInputEvent;
}

async function sendImageTurn(
  connection: ImageTurnConnection,
  event: ImageInputEvent,
): Promise<void> {
  await connection.sendEvent(event);
  await connection.requestResponse();
}
// </image_turn>

async function selfTest(): Promise<void> {
  const event = buildImageEvent("data:image/png;base64,iVBORw==", "  ");
  let itemCount = 0;
  let responseCount = 0;
  const connection: ImageTurnConnection = {
    async sendEvent(value) {
      itemCount++;
      assert(value === event, "The item event changed before send.");
    },
    async requestResponse() {
      responseCount++;
    },
  };

  await sendImageTurn(connection, event);
  assert(event.item.content.map((part) => part.type).join(",") === "input_text,input_image");
  assert(event.item.content[0].type === "input_text");
  assert(event.item.content[0].text === defaultImagePrompt);
  assert(event.item.content[1].type === "input_image");
  assert(event.item.content[1].image_url?.startsWith("data:image/png;base64,"));
  assert(event.item.content[1].detail === "low");
  assert(itemCount === 1, "Expected exactly one conversation item.");
  assert(responseCount === 1, "Expected exactly one response request.");
  assert(validateImage("boundary.png", maxImageBytes) === "image/png");
  assertThrows(() => validateImage("oversize.png", maxImageBytes + 1), "8 MiB");
  assertThrows(() => validateImage("unsupported.gif", 1), "JPEG, PNG, or WebP");
  console.log("Image payload validation passed.");
}

function assert(condition: unknown, message = "Image payload self-test failed."): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function assertThrows(action: () => void, expectedMessage: string): void {
  try {
    action();
  } catch (error) {
    assert(error instanceof Error && error.message.includes(expectedMessage));
    return;
  }
  throw new Error("Expected validation to fail.");
}

function requiredEnvironmentVariable(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Set ${name} before running the sample.`);
  }
  return value;
}

async function main(): Promise<void> {
  if (process.argv.includes("--self-test")) {
    await selfTest();
    return;
  }

  const endpoint = requiredEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
  const agentName = requiredEnvironmentVariable("FOUNDRY_VOICE_AGENT_NAME");
  const imagePath = requiredEnvironmentVariable("FOUNDRY_VOICE_AGENT_IMAGE_PATH");
  const prompt = process.env.FOUNDRY_VOICE_AGENT_IMAGE_PROMPT || defaultImagePrompt;
  const event = buildImageEvent(await imageDataUrl(imagePath), prompt);
  const project = new AIProjectClient(endpoint, new DefaultAzureCredential());
  const connection = await project.beta.voiceAgents.realtime.connect(agentName);

  try {
    await sendImageTurn(connection, event);
    for await (const serverEvent of connection) {
      if (serverEvent.type === "response.output_text.done") {
        console.log(`Agent: ${serverEvent.text}`);
      } else if (serverEvent.type === "response.output_audio_transcript.done") {
        console.log(`Agent: ${serverEvent.transcript}`);
      } else if (serverEvent.type === "error") {
        throw new Error(
          `${serverEvent.error.code ?? "voice_agent_error"}: ${serverEvent.error.message}`,
        );
      } else if (serverEvent.type === "response.done") {
        if (serverEvent.response.status !== "completed") {
          throw new Error(`Response status: ${serverEvent.response.status}`);
        }
        await connection.close();
        return;
      }
    }
    throw new Error("The connection closed before response.done.");
  } finally {
    await connection.dispose();
  }
}

main().catch((error: unknown) => {
  console.error("The sample encountered an error:", error);
  process.exitCode = 1;
});
