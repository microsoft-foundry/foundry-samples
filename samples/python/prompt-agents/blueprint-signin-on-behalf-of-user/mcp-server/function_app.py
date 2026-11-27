import azure.functions as func

app = func.FunctionApp()


@app.mcp_tool_trigger(
    arg_name="tool_context",
    tool_name="greet",
    description="Greets the caller.",
    tool_properties="[]",
)
def greet(tool_context: str, context: func.Context) -> str:
    return f"Hello from the agent's tool. Invocation ID: {context.invocation_id}"
