# <complete_code>
# <imports>
import sys
from pathlib import Path

from foundry_local_sdk import (
    ChatSession,
    Configuration,
    FoundryLocalManager,
    MessageItem,
    Request,
    RequestOptions,
    SearchOptions,
    TextItem,
)

# </imports>


def get_text(response):
    parts = []
    for item in response:
        if isinstance(item, TextItem):
            parts.append(item.text)
        elif isinstance(item, MessageItem):
            parts.extend(part.text for part in item.parts if isinstance(part, TextItem))
    return "".join(parts)


def summarize_file(model, file_path, system_prompt):
    """Summarize a single file and print the result."""
    content = Path(file_path).read_text(encoding="utf-8")
    with ChatSession(model) as session:
        session.set_options(
            RequestOptions(
                search=SearchOptions(temperature=0.2, max_output_tokens=512)
            )
        )
        with (
            Request()
            .add_item(MessageItem.system(system_prompt))
            .add_item(MessageItem.user(content)) as request
        ):
            with session.process_request(request) as response:
                print(get_text(response))


def summarize_directory(model, directory, system_prompt):
    """Summarize all .txt files in a directory."""
    txt_files = sorted(Path(directory).glob("*.txt"))

    if not txt_files:
        print(f"No .txt files found in {directory}")
        return

    for txt_file in txt_files:
        print(f"--- {txt_file.name} ---")
        summarize_file(model, txt_file, system_prompt)
        print()


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
    print("Model loaded and ready.\n")
    # </init>

    try:
        # <summarization>
        system_prompt = (
            "Summarize the following document into concise bullet points. "
            "Focus on the key points and main ideas."
        )

        # <file_reading>
        target = sys.argv[1] if len(sys.argv) > 1 else "document.txt"
        target_path = Path(target)
        # </file_reading>

        if target_path.is_dir():
            summarize_directory(model, target_path, system_prompt)
        else:
            print(f"--- {target_path.name} ---")
            summarize_file(model, target_path, system_prompt)
    # </summarization>
    finally:
        # Clean up
        if model.is_loaded:
            model.unload()
        manager.close()
        print("\nModel unloaded. Done!")


if __name__ == "__main__":
    main()
# </complete_code>
