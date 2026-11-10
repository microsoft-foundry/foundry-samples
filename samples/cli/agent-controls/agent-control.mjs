import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { DefaultAzureCredential } from "@azure/identity";
import {
  applyTransformCtx,
  contextIdentity,
  InterceptionPoint,
  validateVerdict,
} from "@responsibleai/agent-hooks";
import canonicalize from "canonicalize";

export const API_VERSION = "2026-10-15-preview";
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
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const nonempty = (value) => typeof value === "string" && value.trim().length > 0;
const sameResource = (left, right) =>
  nonempty(left) && nonempty(right) && left.toLowerCase() === right.toLowerCase();

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

export function requestDigest(context, policyId) {
  return `sha256:${createHash("sha256")
    .update(canonicalize({
      apiVersion: API_VERSION,
      context,
      selectors: { policyId },
    }), "utf8")
    .digest("hex")}`;
}

export function verifyEvaluation(result, context, config) {
  validateVerdict(result?.verdict);
  const receipt = result.receipt;
  assert(receipt?.receiptVersion === API_VERSION, "Unexpected receipt version");
  assert(receipt.profile === "namedPolicy", "Unexpected evaluation profile");
  assert(nonempty(receipt.evaluationId), "Missing evaluation ID");
  assert(Number.isSafeInteger(receipt.attempt) && receipt.attempt > 0, "Invalid attempt");
  assert(receipt.requestBinding?.algorithm === "sha256", "Unexpected digest algorithm");
  assert(receipt.requestBinding?.canonicalization === "rfc8785", "Unexpected canonicalization");
  assert(
    receipt.requestBinding.digest === requestDigest(context, config.policyId),
    "Receipt does not match the request",
  );
  assert(
    receipt.evaluatedInterventionPoint === context.interception_point,
    "Receipt does not match the interception point",
  );
  assert(
    Array.isArray(receipt.requiredInterventionPoints) &&
      receipt.requiredInterventionPoints.includes(context.interception_point) &&
      receipt.requiredInterventionPoints.every((point) => POINTS.includes(point)),
    "The policy requires an unsupported interception point",
  );
  assert(nonempty(receipt.hostProfileVersion), "Missing host profile version");
  assert(
    sameResource(receipt.authenticatedProducerResourceId, config.producerResourceId),
    "Unexpected authenticated producer",
  );
  assert(
    Array.isArray(receipt.evaluatedPolicyLayers) && receipt.evaluatedPolicyLayers.length > 0,
    "No policy layers were evaluated",
  );
  for (const layer of receipt.evaluatedPolicyLayers) {
    assert(nonempty(layer.kind) && nonempty(layer.policyResourceId), "Incomplete policy layer");
    assert(nonempty(layer.policyRevision), "Missing policy revision");
    assert(DIGEST.test(layer.policySemanticDigest), "Invalid policy digest");
    assert(DIGEST.test(layer.manifestRegoDigest), "Invalid manifest/Rego digest");
    assert(["allow", "deny", "transform"].includes(layer.decision), "Invalid layer decision");
  }
  assert(
    !receipt.evaluatedPolicyLayers.some((layer) => layer.decision === "deny") ||
      result.verdict.decision === "deny",
    "The aggregate verdict does not preserve a policy deny",
  );
  assert(
    !receipt.evaluatedPolicyLayers.some((layer) => layer.decision === "transform") ||
      result.verdict.decision !== "allow",
    "The aggregate verdict does not preserve a policy transform",
  );
  const primary = receipt.evaluatedPolicyLayers.filter((layer) => layer.kind === "namedPolicy");
  assert(
    primary.length === 1 && sameResource(primary[0].policyResourceId, config.policyId),
    "The expected named policy was not evaluated",
  );
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
    super(`Agent Control denied the action: ${evaluation.verdict.reason ?? "policy_denied"}`);
    this.name = "PolicyDenied";
    this.evaluation = evaluation;
  }
}

export class AgentControlClient {
  constructor(config) {
    assert(nonempty(config.policyId) && nonempty(config.producerResourceId), "Policy and producer IDs are required");
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
    this.url.searchParams.set("policyId", config.policyId);
  }

  async evaluate(context) {
    validateJson(context);
    assert(POINTS.includes(context.interception_point), "Unsupported interception point");
    let payload = context;
    for (const field of TARGET_FIELDS[context.interception_point]) payload = payload?.[field];
    assert(payload !== undefined, "Missing point-specific payload");
    assert.deepEqual(context.target, payload, "The target must equal the point-specific payload");
    contextIdentity(context);
    const body = JSON.stringify(context);
    assert(Buffer.byteLength(body, "utf8") <= LIMIT, "The request exceeds 1,048,576 bytes");
    const sent = JSON.parse(body);
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
      const result = await readJson(response);
      if (!response.ok) {
        throw new Error(`Agent Control HTTP ${response.status}: ${result.error?.code ?? "unknown_error"}`);
      }
      verifyEvaluation(result, sent, this.config);
      assert(Date.now() < deadline, "The evaluation deadline expired");
      const approved = result.verdict.decision === "transform"
        ? applyTransformCtx(sent, result.verdict.transform.path, result.verdict.transform.value ?? null)
        : sent;
      return { ...result, context: approved };
    } finally {
      clearTimeout(timer);
    }
  }

  async guard(context, action) {
    const evaluation = await this.evaluate(context);
    if (evaluation.verdict.decision === "deny") throw new PolicyDenied(evaluation);
    return { value: await action(evaluation.context), receipt: evaluation.receipt };
  }
}

export function clientFromEnvironment() {
  for (const name of ["AGENT_CONTROL_ENDPOINT", "AGENT_CONTROL_ACCOUNT_ID", "AGENT_CONTROL_POLICY_ID"]) {
    assert(nonempty(process.env[name]), `Set ${name} before running the sample`);
  }
  return new AgentControlClient({
    endpoint: process.env.AGENT_CONTROL_ENDPOINT,
    policyId: process.env.AGENT_CONTROL_POLICY_ID,
    producerResourceId: process.env.AGENT_CONTROL_PRODUCER_ID ?? process.env.AGENT_CONTROL_ACCOUNT_ID,
  });
}
