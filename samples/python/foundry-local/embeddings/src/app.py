# <complete_code>
# <imports>
from foundry_local_sdk import (
    Configuration,
    EmbeddingsSession,
    FoundryLocalManager,
    Request,
    TensorItem,
    TextItem,
)

# </imports>


def download_if_needed(model) -> None:
    if model.is_cached:
        print(f"Using cached model {model.id}.")
        return
    model.download(
        lambda progress: print(
            f"\rDownloading model: {progress:.2f}%",
            end="",
            flush=True,
        )
    )
    print()


def main():
    # <init>
    # Initialize the Foundry Local SDK
    config = Configuration(app_name="foundry_local_samples")
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    # Select and load an embedding model from the catalog.
    model = manager.catalog.get_model("qwen3-embedding-0.6b")
    if model is None:
        raise RuntimeError("Model 'qwen3-embedding-0.6b' was not found in the catalog.")

    download_if_needed(model)
    model.load()
    print("Model loaded and ready.")
    # </init>

    try:
        with EmbeddingsSession(model) as session:
            # <single_embedding>
            # Generate a single embedding.
            print("\n--- Single Embedding ---")
            with Request().add_item(
                TextItem("The quick brown fox jumps over the lazy dog")
            ) as request:
                with session.process_request(request) as response:
                    embedding = next(
                        item for item in response if isinstance(item, TensorItem)
                    )
                    print(f"Dimensions: {embedding.dimensions}")
                    print(f"First 5 values: {embedding.data[:5]}")
            # </single_embedding>

            # <batch_embedding>
            # Generate embeddings for multiple inputs.
            print("\n--- Batch Embeddings ---")
            inputs = [
                "Machine learning is a subset of artificial intelligence",
                "The capital of France is Paris",
                "Rust is a systems programming language",
            ]
            with Request() as request:
                for text in inputs:
                    request.add_item(TextItem(text))
                with session.process_request(request) as response:
                    embeddings = [
                        item for item in response if isinstance(item, TensorItem)
                    ]
                    print(f"Number of embeddings: {len(embeddings)}")
                    for index, embedding in enumerate(embeddings):
                        print(f"  [{index}] Dimensions: {embedding.dimensions}")
    # </batch_embedding>
    finally:
        # Clean up
        if model.is_loaded:
            model.unload()
        manager.close()
        print("\nModel unloaded.")


if __name__ == "__main__":
    main()
# </complete_code>
