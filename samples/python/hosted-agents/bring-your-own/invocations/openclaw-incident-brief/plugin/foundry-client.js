import { DefaultAzureCredential } from "@azure/identity";

const TOKEN_SCOPE = "https://ai.azure.com/.default";
const REQUEST_TIMEOUT_MS = 120_000;

export class FoundryClient {
  constructor(config, { credential = new DefaultAzureCredential(), fetchImpl = fetch } = {}) {
    if (!config?.projectEndpoint || !config.agentName || !config.sessionId) {
      throw new Error("Configure projectEndpoint, agentName, and sessionId for the Foundry plugin.");
    }
    const project = new URL(config.projectEndpoint);
    if (project.protocol !== "https:" || project.username || project.password || project.search || project.hash) {
      throw new Error("projectEndpoint must be an HTTPS Foundry project URL without credentials or a query.");
    }
    this.endpoint = `${project.href.replace(/\/$/, "")}/agents/${encodeURIComponent(config.agentName)}/endpoint/protocols/invocations`;
    this.sessionId = config.sessionId;
    this.credential = credential;
    this.fetch = fetchImpl;
  }

  async request(method, invocationId, body, signal) {
    const url = new URL(this.endpoint + (invocationId ? `/${encodeURIComponent(invocationId)}` : ""));
    url.searchParams.set("api-version", "v1");
    url.searchParams.set("agent_session_id", this.sessionId);
    const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
    const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
    const token = await this.credential.getToken(TOKEN_SCOPE, { abortSignal: requestSignal });
    if (!token?.token) {
      throw new Error("Azure authentication returned no access token.");
    }
    const response = await this.fetch(url, {
      method,
      signal: requestSignal,
      headers: { authorization: `Bearer ${token.token}`, "content-type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error(`Foundry returned a non-JSON response (HTTP ${response.status}).`, { cause: error });
    }
    if (!response.ok) {
      const message = typeof data?.error === "string" ? data.error : data?.error?.message;
      throw new Error(`Foundry request failed (HTTP ${response.status}): ${message || "unknown error"}`);
    }
    if (
      !data ||
      typeof data !== "object" ||
      !["pending", "completed", "failed"].includes(data.status) ||
      typeof data.invocation_id !== "string" ||
      typeof data.job_id !== "string" ||
      data.session_id !== this.sessionId ||
      (invocationId && data.invocation_id !== invocationId) ||
      (method === "GET" && data.status === "completed" &&
        (typeof data.brief !== "string" || !data.brief.trim())) ||
      (method === "GET" && data.status === "failed" && typeof data.error !== "string")
    ) {
      throw new Error("Foundry returned an invalid incident-brief response.");
    }
    return data;
  }

  start(requestId, updates, signal) {
    return this.request("POST", undefined, { request_id: requestId, updates }, signal);
  }

  status(invocationId, signal) {
    return this.request("GET", invocationId, undefined, signal);
  }
}
