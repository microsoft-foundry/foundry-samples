import assert from "node:assert/strict";
import { DefaultAzureCredential } from "@azure/identity";
import {
  applyTransformCtx,
  contextIdentity,
  InterceptionPoint,
  validateTransformCtx,
} from "@responsibleai/agent-hooks";

export const API_VERSION = "2026-09-01-preview";
const SCOPE = "https://cognitiveservices.azure.com/.default";
const LIMIT = 1_048_576;
const POINTS = Object.values(InterceptionPoint);
const TARGET_FIELDS = {
  agent_startup: ["agent_init"],
  input: ["input"],
  pre_model_call: ["messages"],
  post_model_call: ["response"],
  pre_tool_call: ["tool_call", "args"],
  post_tool_call: ["tool_result", "value"],
  output: ["output"],
  agent_shutdown: ["summary"],
};
const nonempty = (value) => typeof value === "string" && value.trim().length > 0;
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

export function validateJson(value, depth = 0) {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    assert(value.isWellFormed(), "JSON strings must contain valid Unicode");
    return;
  }
  if (typeof value === "number") {
    assert(Number.isFinite(value), "JSON numbers must be finite");
    return;
  }
  assert(value && typeof value === "object", "Only native JSON values are supported");
  assert(depth < 64, "JSON exceeds container depth 64");
  if (Array.isArray(value)) {
    for (const item of value) validateJson(item, depth + 1);
    return;
  }
  assert(
    Object.getPrototypeOf(value) === Object.prototype ||
      Object.getPrototypeOf(value) === null,
    "JSON objects must be plain objects",
  );
  for (const [key, item] of Object.entries(value)) {
    assert(key.isWellFormed(), "JSON member names must contain valid Unicode");
    validateJson(item, depth + 1);
  }
}

function toRequest(context, policyId) {
  const source = context.interception_point;
  let content = context.target;
  if (source === "input" || source === "output") {
    assert(nonempty(content.content), "Input and output require nonempty text");
    if (source === "input") assert(content.role === "user", "Input source requires the user role");
    content = content.content;
  } else {
    if (source === "pre_model_call") {
      content = { messages: context.messages };
      if (context.tools !== undefined) content.tools = context.tools;
    }
    assert(content !== null, "Content must not be JSON null");
    content = JSON.stringify(content);
  }
  const request = {
    policyId,
    source,
    content,
    context: {
      agentId: context.agent.id,
      sessionId: context.session.id,
      sequence: context.sequence,
    },
  };
  if (context.extensions !== undefined) {
    request.context.extensions = JSON.stringify(context.extensions);
  }
  if (source === "pre_model_call" || source === "post_model_call") {
    request.modelId = context.model.id;
    if (context.request_id !== undefined) request.modelRequestId = context.request_id;
  }
  if (source === "pre_tool_call" || source === "post_tool_call") {
    request.toolName = context.tool_call.name;
    request.toolCallId = context.tool_call.id;
  }
  if (source === "post_tool_call") {
    request.toolArguments = JSON.stringify(context.tool_call.args);
    request.toolResultIsError = context.tool_result.is_error;
    if (context.tool_result.duration_ms !== undefined) {
      request.toolDurationMs = context.tool_result.duration_ms;
    }
  }
  return request;
}

export function verifyEvaluation(result, context, request) {
  assert(["allowed", "blocked"].includes(result?.verdict), "Invalid enforcement verdict");
  const decision = result.acsVerdict?.decision;
  assert(["allow", "deny", "transform"].includes(decision), "Invalid ACS decision");
  assert(
    (result.verdict === "blocked") === (decision === "deny"),
    "The enforcement verdict and ACS decision disagree",
  );
  if (decision === "deny") return context;
  assert(typeof result.content === "string", "Missing allowed content");
  const textSource = request.source === "input" || request.source === "output";
  const content = textSource ? result.content : JSON.parse(result.content);
  validateJson(content);
  if (decision === "allow") {
    assert.deepEqual(content, textSource ? request.content : JSON.parse(request.content),
      "An allow must preserve the evaluated content");
    return context;
  }
  assert(textSource || request.source === "pre_tool_call" || request.source === "post_tool_call",
    "Model and lifecycle transforms are not supported");
  const transform = result.acsVerdict.transform;
  assert(nonempty(transform?.path) && typeof transform.value === "string", "Invalid transform metadata");
  assert(textSource ? transform.path === "$target.content" :
    transform.path === "$target" || transform.path.startsWith("$target.") || transform.path.startsWith("$target["),
  "Invalid transform path");
  const replacement = JSON.parse(transform.value);
  validateJson(replacement);
  validateTransformCtx(context, transform.path, replacement);
  assert(textSource ? nonempty(content) : content !== null, "Invalid transformed content");
  if (request.source === "pre_tool_call") assert(isObject(content), "Transformed tool arguments must be an object");
  // The service has applied the transform; replace the target with its final content.
  return applyTransformCtx(context, textSource ? "$target.content" : "$target", content);
}

async function readJson(response) {
  assert(response.body, "The service returned an empty body");
  const reader = response.body.getReader();
  const chunks = [];
  let bytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > LIMIT) {
        await reader.cancel();
        throw new Error("The response exceeds 1,048,576 bytes");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const result = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)));
  validateJson(result);
  return result;
}

export class PolicyDenied extends Error {
  constructor(evaluation) {
    super(`Agent Control denied the action: ${evaluation.reason ?? evaluation.acsVerdict.reason ?? "policy_denied"}`);
    this.name = "PolicyDenied";
    this.evaluation = evaluation;
  }
}

export class AgentControlClient {
  constructor(config) {
    assert(nonempty(config.policyId), "A policy ID is required");
    const endpoint = new URL(config.endpoint);
    assert(
      endpoint.protocol === "https:" && endpoint.pathname === "/" &&
        !endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash,
      "Use the account's HTTPS origin as the endpoint",
    );
    this.config = { ...config };
    this.timeoutMs = config.timeoutMs ?? 30_000;
    assert(
      Number.isSafeInteger(this.timeoutMs) && this.timeoutMs > 0 && this.timeoutMs <= 30_000,
      "Use an operation timeout between 1 and 30,000 milliseconds",
    );
    this.credential = config.credential ?? new DefaultAzureCredential();
    this.fetch = config.fetch ?? globalThis.fetch;
    this.url = new URL("/contentsafety/content:unifiedModerate", endpoint);
    this.url.searchParams.set("api-version", API_VERSION);
  }

  async evaluate(context) {
    validateJson(context);
    assert(POINTS.includes(context.interception_point), "Unsupported interception point");
    let payload = context;
    for (const field of TARGET_FIELDS[context.interception_point]) payload = payload?.[field];
    assert(payload !== undefined, "Missing point-specific payload");
    assert.deepEqual(context.target, payload, "The target must equal the point-specific payload");
    contextIdentity(context);
    const sent = JSON.parse(JSON.stringify(context));
    const request = toRequest(sent, this.config.policyId);
    const body = JSON.stringify(request);
    assert(Buffer.byteLength(body, "utf8") <= LIMIT, "The request exceeds 1,048,576 bytes");
    const controller = new AbortController();
    const deadline = Date.now() + this.timeoutMs;
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const token = await this.credential.getToken(SCOPE, { abortSignal: controller.signal });
      assert(nonempty(token?.token), "No access token was returned");
      controller.signal.throwIfAborted();
      const response = await this.fetch(this.url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token.token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body,
        redirect: "error",
        signal: controller.signal,
      });
      let result;
      try {
        result = await readJson(response);
      } catch (error) {
        if (!response.ok) {
          throw new Error(`Agent Control HTTP ${response.status}: unreadable error response`, { cause: error });
        }
        throw error;
      }
      if (!response.ok) {
        throw new Error(`Agent Control HTTP ${response.status}: ${result.error?.code ?? "unknown_error"}`);
      }
      const approved = verifyEvaluation(result, sent, request);
      assert(Date.now() < deadline, "The evaluation deadline expired");
      return { ...result, context: approved };
    } finally {
      clearTimeout(timer);
    }
  }

  async guard(context, action) {
    const evaluation = await this.evaluate(context);
    if (evaluation.verdict === "blocked") throw new PolicyDenied(evaluation);
    return { value: await action(evaluation.context), evaluation };
  }
}

export function clientFromEnvironment() {
  for (const name of ["AGENT_CONTROL_ENDPOINT", "AGENT_CONTROL_POLICY_ID"]) {
    assert(nonempty(process.env[name]), `Set ${name} before running the sample`);
  }
  return new AgentControlClient({
    endpoint: process.env.AGENT_CONTROL_ENDPOINT,
    policyId: process.env.AGENT_CONTROL_POLICY_ID,
  });
}
