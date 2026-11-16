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
    eps = manager.discover_eps()
    missing_eps = [ep.name for ep in eps if not ep.is_registered]
    if missing_eps:
        manager.download_and_register_eps(missing_eps)

    # Select and load a model from the catalog.
    model = manager.catalog.get_model("qwen2.5-0.5b")
    if model is None:
        raise RuntimeError("Model 'qwen2.5-0.5b' was not found in the catalog.")
    if not model.is_cached:
        model.download(
            lambda progress: print(
                f"\rDownloading model: {progress:.2f}%",
                end="",
                flush=True,
            )
        )
        print()
    model.load()
    print("Model loaded and ready.")
    # </init>

    try:
        # <streaming>
        # Create a native chat session and stream the response token by token.
        with ChatSession(model) as session:
            session.set_options(
                RequestOptions(
                    search=SearchOptions(temperature=0.0, max_output_tokens=256)
                )
            )
            session.set_streaming(True)
            with Request().add_item(
                MessageItem.user("What is the golden ratio?")
            ) as request:
                print("Assistant: ", end="", flush=True)
                with session.process_streaming_request(request) as stream:
                    for item in stream:
                        if (
                            isinstance(item, TextItem)
                            and item.type == TextItemType.DEFAULT
                        ):
                            print(item.text, end="", flush=True)
                print()
    # </streaming>
    finally:
        # Clean up
        if model.is_loaded:
            model.unload()
        manager.close()
        print("Model unloaded.")


if __name__ == "__main__":
    main()
# </complete_code>
