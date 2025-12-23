export type Using = string | { namespace: string; condition?: boolean };

export function usings(...items: Using[]): string {
  return items
    .filter((u) => typeof u === "string" || u.condition)
    .map((u) => `using ${typeof u === "string" ? u : u.namespace};`)
    .join("\n");
}

export function valueOrEnvironment(
  useEnvironmentVariable: boolean,
  variableName: string,
  environmentVariable: string,
  value?: string,
): string {
  if (useEnvironmentVariable && environmentVariable) {
    return `var ${variableName} = Environment.GetEnvironmentVariable("${environmentVariable}") ?? throw new InvalidOperationException("${environmentVariable} environment variable is not set.")`;
  } else if (value) {
    return `const string ${variableName} = "${value}";`;
  } else {
    console.error("No value provided for variable or environment variable.");
    process.exit(1);
  }
}
