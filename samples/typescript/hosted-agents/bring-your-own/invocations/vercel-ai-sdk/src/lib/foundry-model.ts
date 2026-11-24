import { DefaultAzureCredential } from "@azure/identity";
import { createOpenAI } from "@ai-sdk/openai";

const tokenScope = "https://ai.azure.com/.default";
let credential: DefaultAzureCredential | undefined;

type FoundryModelOptions = {
  endpoint: string;
  deployment: string;
  apiKey: string | (() => Promise<string>);
  fetch?: typeof globalThis.fetch;
};

// Foundry Responses requires `type` on every input item, but the AI SDK omits
// `type: "message"` on role-based messages.
export function withMessageTypes(
  baseFetch: typeof globalThis.fetch = globalThis.fetch,
): typeof globalThis.fetch {
  return async (input, init) => {
    if (typeof init?.body === "string") {
      const body = JSON.parse(init.body) as { input?: unknown };
      if (Array.isArray(body.input)) {
        body.input = body.input.map((item: unknown) =>
          item && typeof item === "object" && "role" in item && !("type" in item)
            ? { type: "message", ...item }
            : item,
        );
        init = { ...init, body: JSON.stringify(body) };
      }
    }
    return baseFetch(input, init);
  };
}

export function createFoundryResponsesModel({
  endpoint,
  deployment,
  apiKey,
  fetch,
}: FoundryModelOptions) {
  const provider = createOpenAI({
    baseURL: `${endpoint.replace(/\/+$/, "")}/openai/v1`,
    apiKey,
    fetch: withMessageTypes(fetch),
  });

  return provider.responses(deployment);
}

export function getFoundryModel() {
  const endpoint = process.env.FOUNDRY_PROJECT_ENDPOINT;
  const deployment = process.env.AZURE_AI_MODEL_DEPLOYMENT_NAME;
  if (!endpoint) {
    throw new Error("FOUNDRY_PROJECT_ENDPOINT is required.");
  }
  if (!deployment) {
    throw new Error("AZURE_AI_MODEL_DEPLOYMENT_NAME is required.");
  }

  const tokenCredential = (credential ??= new DefaultAzureCredential());
  return createFoundryResponsesModel({
    endpoint,
    deployment,
    apiKey: async () => {
      const token = await tokenCredential.getToken(tokenScope);
      if (!token) {
        throw new Error("Could not acquire a Foundry access token.");
      }
      return token.token;
    },
  });
}
