// <complete_code>
// <imports>
using Microsoft.AI.Foundry.Local;
// </imports>

// <init>
var config = new Configuration
{
    AppName = "foundry_local_samples",
    LogLevel = Microsoft.AI.Foundry.Local.LogLevel.Information
};

// Initialize the singleton instance.
await FoundryLocalManager.CreateAsync(config, Utils.GetAppLogger());
var mgr = FoundryLocalManager.Instance;
// </init>

// <model_setup>
// Get the model catalog
var catalog = await mgr.GetCatalogAsync();

// Get an embedding model
var model = await catalog.GetModelAsync("qwen3-embedding-0.6b") ?? throw new Exception("Embedding model not found");

// Download the model (the method skips download if already cached)
await model.DownloadAsync(progress =>
{
    Console.Write($"\rDownloading model: {progress:F2}%");
    if (progress >= 100f)
    {
        Console.WriteLine();
    }
});

// Load the model
Console.Write($"Loading model {model.Id}...");
await model.LoadAsync();
Console.WriteLine("done.");
// </model_setup>

// <single_embedding>
// Create a native embeddings session.
using var embeddingSession = new EmbeddingsSession(model);

// Generate a single embedding
Console.WriteLine("\n--- Single Embedding ---");
using var singleRequest = new Request();
singleRequest.AddItem(new TextItem("The quick brown fox jumps over the lazy dog"));
using var response = await embeddingSession.ProcessRequestAsync(singleRequest);
var embedding = (TensorItem)response.GetItem(0);
var values = embedding.ToArray<float>();
Console.WriteLine($"Dimensions: {embedding.ElementCount}");
Console.WriteLine($"First 5 values: [{string.Join(", ", values.Take(5).Select(v => v.ToString("F6")))}]");
// </single_embedding>

// <batch_embedding>
// Generate embeddings for multiple inputs
Console.WriteLine("\n--- Batch Embeddings ---");
using var batchRequest = new Request();
foreach (var input in new[]
{
    "Machine learning is a subset of artificial intelligence",
    "The capital of France is Paris",
    "C# is a modern programming language"
})
{
    batchRequest.AddItem(new TextItem(input));
}
using var batchResponse = await embeddingSession.ProcessRequestAsync(batchRequest);

Console.WriteLine($"Number of embeddings: {batchResponse.ItemCount}");
for (var i = 0; i < batchResponse.ItemCount; i++)
{
    var tensor = (TensorItem)batchResponse.GetItem(i);
    Console.WriteLine($"  [{i}] Dimensions: {tensor.ElementCount}");
}
// </batch_embedding>

// <cleanup>
// Tidy up - unload the model
batchResponse.Dispose();
batchRequest.Dispose();
response.Dispose();
singleRequest.Dispose();
embeddingSession.Dispose();
await model.UnloadAsync();
Console.WriteLine("\nModel unloaded.");
// </cleanup>
// </complete_code>
