# <complete_code>
# <imports>
import json

from foundry_local_sdk import (
    ChatSession,
    Configuration,
    FoundryLocalManager,
    MessageItem,
    Request,
    RequestOptions,
    SearchOptions,
    TextItem,
    ToolCallItem,
    ToolResultItem,
)

# </imports>


# <tool_definitions>
# --- Tool definitions ---
tools = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city or location",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit",
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "calculate",
        "description": "Perform a math calculation",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The math expression to evaluate",
                }
            },
            "required": ["expression"],
        },
    },
]


# --- Tool implementations ---
def get_weather(location, unit="celsius"):
    """Simulate a weather lookup."""
    return {
        "location": location,
        "temperature": 22 if unit == "celsius" else 72,
        "unit": unit,
        "condition": "Sunny",
    }


def calculate(expression):
    """Evaluate a math expression safely."""
    allowed = set("0123456789+-*/(). ")
    if not all(character in allowed for character in expression):
        return {"error": "Invalid expression"}
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return {"expression": expression, "result": result}
    except Exception as error:
        return {"error": str(error)}


tool_functions = {"get_weather": get_weather, "calculate": calculate}
# </tool_definitions>


def response_content(response):
    text_parts = []
    tool_calls = []
    for item in response:
        parts = item.parts if isinstance(item, MessageItem) else [item]
        for part in parts:
            if isinstance(part, TextItem):
                text_parts.append(part.text)
            elif isinstance(part, ToolCallItem):
                tool_calls.append((part.call_id, part.name, part.arguments))
    return "".join(text_parts), tool_calls


# <tool_loop>
def process_tool_calls(session, answer, pending_calls):
    """Handle tool calls until the stateful session produces a final answer."""
    while pending_calls:
        with Request() as follow_up:
            for call_id, function_name, arguments_json in pending_calls:
                arguments = json.loads(arguments_json)
                print(f"  Tool call: {function_name}({arguments})")
                result = tool_functions[function_name](**arguments)
                follow_up.add_item(
                    ToolResultItem(call_id=call_id, result=json.dumps(result))
                )

            with session.process_request(follow_up) as next_response:
                answer, pending_calls = response_content(next_response)

    return answer


# </tool_loop>


# <init>
def main():
    # Initialize the Foundry Local SDK
    config = Configuration(app_name="foundry_local_samples")
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    # Discover and register execution providers that are not already available.
    missing_eps = [ep.name for ep in manager.discover_eps() if not ep.is_registered]
    if missing_eps:
        manager.download_and_register_eps(missing_eps)

    # Select and load a tool-capable model.
    model = manager.catalog.get_model("qwen2.5-0.5b")
    if model is None:
        raise RuntimeError("Model 'qwen2.5-0.5b' was not found in the catalog.")
    if not model.is_cached:
        model.download(
            lambda progress: print(
                f"\rDownloading model: {progress:.2f}%", end="", flush=True
            )
        )
        print()
    model.load()
    print("Model loaded and ready.")

    try:
        with ChatSession(model) as session:
            session.set_options(
                RequestOptions(
                    search=SearchOptions(temperature=0.0, max_output_tokens=512)
                )
            )
            for tool in tools:
                session.add_tool_definition(
                    tool["name"],
                    tool["description"],
                    json.dumps(tool["parameters"]),
                )

            with (
                Request()
                .add_item(
                    MessageItem.system(
                        "You are a helpful assistant with access to tools. "
                        "Use them when needed to answer questions accurately."
                    )
                )
                .add_item(
                    MessageItem.user(
                        "What is the weather in Seattle and what is 42 * 17?"
                    )
                ) as request
            ):
                print("Sending request with tools...")
                with session.process_request(request) as response:
                    answer, pending_calls = response_content(response)
                answer = process_tool_calls(session, answer, pending_calls)

            print(f"\nAssistant: {answer}")
    finally:
        # Clean up
        if model.is_loaded:
            model.unload()
        manager.close()
        print("Model unloaded.")


# </init>


if __name__ == "__main__":
    main()
# </complete_code>
