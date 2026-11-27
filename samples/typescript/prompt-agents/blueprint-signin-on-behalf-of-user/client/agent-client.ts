import { DeviceCodeCredential, getBearerTokenProvider } from "@azure/identity";
import OpenAI from "openai";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Set ${name} before running the client.`);
  }
  return value;
}

function findConsentLink(output: readonly unknown[]): string | undefined {
  for (const item of output) {
    if (
      typeof item !== "object" ||
      item === null ||
      !("type" in item) ||
      item.type !== "oauth_consent_request"
    ) {
      continue;
    }
    if (
      !("consent_link" in item) ||
      typeof item.consent_link !== "string" ||
      !URL.canParse(item.consent_link) ||
      new URL(item.consent_link).protocol !== "https:"
    ) {
      throw new Error(
        "The agent requested MCP consent without a valid HTTPS consent link.",
      );
    }
    return item.consent_link;
  }
  return undefined;
}

async function main(): Promise<number> {
  const tenantId = required("AZURE_TENANT_ID");
  const blueprintId = required("GREETING_BLUEPRINT_ID");
  const clientId = required("GREETING_CLIENT_ID");
  const endpoint = new URL(required("GREETING_AGENT_ENDPOINT"));
  if (endpoint.protocol !== "https:") {
    throw new Error("The agent endpoint must use HTTPS.");
  }

  const defaultQuery = Object.fromEntries(endpoint.searchParams);
  endpoint.search = "";
  endpoint.hash = "";
  const credential = new DeviceCodeCredential({
    tenantId,
    clientId,
    userPromptCallback: (info) => console.error(info.message),
  });
  const tokenProvider = getBearerTokenProvider(
    credential,
    `api://${blueprintId}/access_agent`,
  );
  const client = new OpenAI({
    baseURL: endpoint.toString(),
    apiKey: tokenProvider,
    defaultQuery,
  });
  const response = await client.responses.create({
    input: "Call the greet tool once and report its greeting and invocation ID verbatim.",
  });

  // Foundry's consent item is not part of the OpenAI SDK's output union.
  const consentLink = findConsentLink(response.output);
  if (consentLink) {
    console.error(
      "The MCP tool needs your consent. Open this link, sign in as the same user, " +
        `and review the requested permission: ${consentLink}`,
    );
    console.error("After consenting, run the client again.");
    return 2;
  }

  if (!response.output_text.trim()) {
    throw new Error("The agent did not return an answer.");
  }
  console.log(response.output_text);
  return 0;
}

try {
  process.exitCode = await main();
} catch (error) {
  if (error instanceof OpenAI.APIError) {
    console.error(
      `The agent request failed: ${error.status ? `HTTP ${error.status}. ` : ""}${error.message}`,
    );
  } else {
    console.error(
      `Sample failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
  process.exitCode = 1;
}
