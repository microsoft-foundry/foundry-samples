# <complete_code>
# <imports>
from foundry_local_sdk import (
    ChatSession,
    Configuration,
    FoundryLocalManager,
    MessageItem,
    Request,
    RequestOptions,
    SearchOptions,
    TextItem,
    TextItemType,
)

# </imports>


def main():
    # <init>
    # Initialize the Foundry Local SDK
    config = Configuration(app_name="foundry_local_samples")
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    # Discover and register execution providers that are not already available.
    missing_eps = [ep.name for ep in manager.discover_eps() if not ep.is_registered]
    if missing_eps:
        manager.download_and_register_eps(missing_eps)

    # Select and load a model from the catalog.
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
    # </init>

    try:
        # <system_prompt>
        # Start the conversation with a system prompt.
        system_prompt = (
            "You are a helpful, friendly assistant. Keep your responses "
            "concise and conversational. If you don't know something, say so."
        )
        # </system_prompt>

        print("\nChat assistant ready! Type 'quit' to exit.\n")

        with ChatSession(model) as session:
            session.set_options(
                RequestOptions(
                    search=SearchOptions(temperature=0.7, max_output_tokens=512)
                )
            )
            session.set_streaming(True)
            first_turn = True

            # <conversation_loop>
            while True:
                user_input = input("You: ")
                if user_input.strip().lower() in ("quit", "exit"):
                    break

                # <streaming>
                # The stateful session retains earlier turns automatically.
                with Request() as request:
                    if first_turn:
                        request.add_item(MessageItem.system(system_prompt))
                        first_turn = False
                    request.add_item(MessageItem.user(user_input))
                    print("Assistant: ", end="", flush=True)
                    with session.process_streaming_request(request) as stream:
                        for item in stream:
                            if (
                                isinstance(item, TextItem)
                                and item.type == TextItemType.DEFAULT
                            ):
                                print(item.text, end="", flush=True)
                    print("\n")
        # </streaming>
    # </conversation_loop>
    finally:
        # Clean up - unload the model
        if model.is_loaded:
            model.unload()
        manager.close()
        print("Model unloaded. Goodbye!")


if __name__ == "__main__":
    main()
# </complete_code>
