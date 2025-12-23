export type Using = string | { namespace: string; condition?: boolean };

export function valueOrEnvironment(
  useEnvironmentVariable: boolean,
  environmentVariable: string,
  value?: string,
): string {
  if (useEnvironmentVariable && environmentVariable) {
    return `System.getenv("${environmentVariable}")`;
  } else if (value) {
    return `"${value}"`;
  } else {
    console.error("No value provided for variable or environment variable.");
    process.exit(1);
  }
}
