import { DefaultAzureCredential } from "@azure/identity";
import { createOpenAI } from "@ai-sdk/openai";

const tokenScope = "https://ai.azure.com/.default";
let credential: DefaultAzureCredential | undefined;

type FoundryChatModelOptions = {
  endpoint: string;
  deployment: string;
  apiKey: string | (() => Promise<string>);
  fetch?: typeof globalThis.fetch;
};

export function createFoundryChatModel({
  endpoint,
  deployment,
  apiKey,
  fetch,
}: FoundryChatModelOptions) {
  const provider = createOpenAI({
    baseURL: `${endpoint.replace(/\/+$/, "")}/openai/v1`,
    apiKey,
    fetch,
  });

  return provider.chat(deployment);
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
  return createFoundryChatModel({
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
