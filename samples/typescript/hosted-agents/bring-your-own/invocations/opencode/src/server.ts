import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { loadSettings, type Settings } from "./config.js";
import { runWorker } from "./worker.js";

const maxBodyBytes = 16 * 1024;
const jobTimeoutMs = 10 * 60 * 1000;

function respond(response: ServerResponse, status: number, error: string): void {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify({ error }));
}

function issueNumber(value: unknown): number | undefined {
  if (typeof value === "number") {
    return Number.isSafeInteger(value) && value > 0 && value <= 999_999_999 ? value : undefined;
  }
  if (typeof value === "string") {
    const match = value.trim().match(
      /^(?:please\s+)?(?:fix\s+)?(?:github\s+)?(?:issue\s*)?#?([1-9]\d{0,8})[.!]?$/i,
    );
    return match ? Number(match[1]) : undefined;
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const body = value as Record<string, unknown>;
    const fields = [body.issue, body.issue_number, body.message, body.input].filter(
      (field) => field !== undefined,
    );
    return fields.length === 1 ? issueNumber(fields[0]) : undefined;
  }
  return undefined;
}

function readBody(request: IncomingMessage): Promise<string | undefined> {
  return new Promise((resolveBody, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    const cleanup = () => {
      request.removeListener("data", onData);
      request.removeListener("end", onEnd);
      request.removeListener("error", onError);
      request.removeListener("aborted", onAborted);
    };
    const onData = (chunk: Buffer) => {
      size += chunk.length;
      if (size > maxBodyBytes) {
        cleanup();
        request.resume();
        resolveBody(undefined);
      } else {
        chunks.push(chunk);
      }
    };
    const onEnd = () => {
      cleanup();
      resolveBody(Buffer.concat(chunks).toString("utf8"));
    };
    const onError = (error: Error) => { cleanup(); reject(error); };
    const onAborted = () => { cleanup(); reject(new Error("Request was aborted.")); };
    request.on("data", onData);
    request.once("end", onEnd);
    request.once("error", onError);
    request.once("aborted", onAborted);
  });
}

function sendEvent(response: ServerResponse, event: string, value: object): void {
  if (!response.destroyed && !response.writableEnded) {
    response.write(`event: ${event}\ndata: ${JSON.stringify(value)}\n\n`);
  }
}

export function createApp(settings: Settings, worker: typeof runWorker = runWorker) {
  let busy = false;
  const server = createServer(async (request, response) => {
    const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
    if (request.method === "GET" && pathname === "/readiness") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ status: "ready" }));
      return;
    }
    if (request.method !== "POST" || pathname !== "/invocations") {
      respond(response, 404, "Not found.");
      return;
    }

    let text: string | undefined;
    try {
      text = await readBody(request);
    } catch (error) {
      if (!response.destroyed) respond(response, 400, "Could not read the request body.");
      console.error("Could not read invocation:", error);
      return;
    }
    if (text === undefined) {
      respond(response, 413, "The request body exceeds 16 KiB.");
      return;
    }
    let body: unknown = text;
    if (request.headers["content-type"]?.includes("application/json")) {
      try {
        body = JSON.parse(text);
      } catch {
        respond(response, 400, "The request body must be valid JSON.");
        return;
      }
    }
    const number = issueNumber(body);
    if (!number) {
      respond(response, 400, 'Provide one issue number, for example "Fix issue #12" or {"issue":12}.');
      return;
    }
    if (busy) {
      respond(response, 429, "This agent instance is already working on an issue.");
      return;
    }

    busy = true;
    const disconnect = new AbortController();
    const signal = AbortSignal.any([disconnect.signal, AbortSignal.timeout(jobTimeoutMs)]);
    response.on("close", () => {
      if (!response.writableEnded) disconnect.abort(new Error("Invocation client disconnected."));
    });
    response.writeHead(200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
    });
    sendEvent(response, "started", { issue: number });
    const heartbeat = setInterval(() => {
      if (!response.destroyed && !response.writableEnded) response.write(": heartbeat\n\n");
    }, 15_000);
    heartbeat.unref();
    try {
      const result = await worker(settings, number, signal, (message) => {
        sendEvent(response, "progress", { message });
      });
      sendEvent(response, "complete", result);
    } catch (error) {
      const message = (error instanceof Error ? error.message : "The worker failed.")
        .replaceAll(settings.githubToken, "[redacted]");
      sendEvent(response, "error", { message });
      console.error("Invocation failed:", message);
    } finally {
      clearInterval(heartbeat);
      busy = false;
      if (!response.destroyed) response.end();
    }
  });
  server.requestTimeout = 30_000;
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const settings = loadSettings(process.env);
  createApp(settings).listen(settings.port, "0.0.0.0", () => {
    console.log(`OpenCode hosted agent listening on port ${settings.port}.`);
  });
}
