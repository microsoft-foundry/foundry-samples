export type Using = string | { namespace: string; condition?: boolean };

export function usings(...items: Using[]): string {
  return items
    .filter((u) => typeof u === "string" || u.condition)
    .map((u) => `using ${typeof u === "string" ? u : u.namespace};`)
    .join("\n");
}

export function valueOrEnvironment(
  useEnvironmentVariable: boolean,
  environmentVariable: string,
  value?: string,
): string {
  if (useEnvironmentVariable && environmentVariable) {
    return `Environment.GetEnvironmentVariable("${environmentVariable}")`;
  } else if (value) {
    return `"${value}"`;
  } else {
    console.error("No value provided for variable or environment variable.");
    process.exit(1);
  }
}
