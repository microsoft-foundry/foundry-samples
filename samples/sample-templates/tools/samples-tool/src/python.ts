export function valueOrEnvironment(
  useEnvironmentVariable: boolean,
  variableName: string,
  environmentVariable: string,
  value?: string,
  indentationLevel: number = 0,
) {
  if (!variableName) {
    console.error("Variable name must be provided.");
    process.exit(1);
  }
  const indent = "  ".repeat(indentationLevel);
  if (useEnvironmentVariable && environmentVariable) {
    return (
      `${variableName} = os.environ.get("${environmentVariable}")\n` +
      `${indent}if not ${variableName}:\n` +
      `${indent}  raise ValueError("Please set the ${environmentVariable} environment variable.")\n`
    );
  } else if (value) {
    return `${variableName} = "${value}"`;
  } else {
    console.error("No value provided for variable or environment variable.");
    process.exit(1);
  }
}
