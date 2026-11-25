import { spawn } from "node:child_process";
import { StringDecoder } from "node:string_decoder";

interface CommandOptions {
  cwd: string;
  env: NodeJS.ProcessEnv;
  signal: AbortSignal;
  input?: string;
  maxOutput?: number;
  secrets?: string[];
}

export async function runCommand(
  command: string,
  args: string[],
  options: CommandOptions,
): Promise<string> {
  options.signal.throwIfAborted();
  const limit = options.maxOutput ?? 1_000_000;
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      detached: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let exceeded = false;
    let terminated = false;
    const stdoutDecoder = new StringDecoder("utf8");
    const stderrDecoder = new StringDecoder("utf8");

    const terminate = () => {
      if (!child.pid || terminated) return;
      terminated = true;
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ESRCH") {
          reject(new Error(`Could not terminate the ${command} process group.`, { cause: error }));
        }
      }
    };
    const capture = (stream: "stdout" | "stderr", chunk: Buffer) => {
      outputBytes += chunk.length;
      if (outputBytes > limit && !exceeded) {
        exceeded = true;
        terminate();
      }
      if (!exceeded) {
        if (stream === "stdout") stdout += stdoutDecoder.write(chunk);
        else stderr += stderrDecoder.write(chunk);
      }
    };
    child.stdout.on("data", (chunk: Buffer) => capture("stdout", chunk));
    child.stderr.on("data", (chunk: Buffer) => capture("stderr", chunk));
    options.signal.addEventListener("abort", terminate, { once: true });
    if (options.signal.aborted) terminate();
    child.stdin.on("error", (error: NodeJS.ErrnoException) => {
      if (error.code !== "EPIPE") console.error("Could not write to child process:", error);
    });
    child.stdin.end(options.input);

    let spawnError: Error | undefined;
    child.on("error", (error) => { spawnError = error; });
    child.on("exit", terminate);
    child.on("close", (code, signal) => {
      options.signal.removeEventListener("abort", terminate);
      stdout += stdoutDecoder.end();
      stderr += stderrDecoder.end();
      if (spawnError) return reject(spawnError);
      if (options.signal.aborted) return reject(options.signal.reason);
      if (exceeded) return reject(new Error(`${command} exceeded its output limit.`));
      if (code !== 0) {
        let detail = [stderr, stdout].filter(Boolean).join("\n").trim().slice(-8_000);
        for (const secret of options.secrets ?? []) {
          if (secret) detail = detail.replaceAll(secret, "[redacted]");
        }
        return reject(new Error(`${command} failed (${signal ?? `exit ${code}`}): ${detail}`));
      }
      resolve(stdout);
    });
  });
}
