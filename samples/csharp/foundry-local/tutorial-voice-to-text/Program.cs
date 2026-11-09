// <complete_code>
// <imports>
using Microsoft.AI.Foundry.Local;
using Microsoft.Extensions.Logging;
using System.Text;
// </imports>

// <init>
CancellationToken ct = CancellationToken.None;

var config = new Configuration
{
    AppName = "foundry_local_samples",
    LogLevel = Microsoft.AI.Foundry.Local.LogLevel.Information
};

using var loggerFactory = LoggerFactory.Create(builder =>
{
    builder.SetMinimumLevel(
        Microsoft.Extensions.Logging.LogLevel.Information
    );
});
var logger = loggerFactory.CreateLogger<Program>();

// Initialize the singleton instance
await FoundryLocalManager.CreateAsync(config, logger);
var mgr = FoundryLocalManager.Instance;

// Download and register all execution providers.
var currentEp = "";
await mgr.DownloadAndRegisterEpsAsync((epName, percent) =>
{
    if (epName != currentEp)
    {
        if (currentEp != "") Console.WriteLine();
        currentEp = epName;
    }
    Console.Write($"\r  {epName.PadRight(30)}  {percent,6:F1}%");
});
if (currentEp != "") Console.WriteLine();

var catalog = await mgr.GetCatalogAsync();
// </init>

// <transcription>
// Load the speech-to-text model
var speechModel = await catalog.GetModelAsync("whisper-tiny")
    ?? throw new Exception("Speech model not found");

await speechModel.DownloadAsync(progress =>
{
    Console.Write($"\rDownloading speech model: {progress:F2}%");
    if (progress >= 100f) Console.WriteLine();
});

await speechModel.LoadAsync();
Console.WriteLine("Speech model loaded.");

// Transcribe the audio file with the native v2 audio session.
var transcriptionText = new StringBuilder();
using var audioSession = new AudioSession(speechModel);
audioSession.SetStreaming(true);
using var audioRequest = new Request();
audioRequest.AddItem(new AudioItem("meeting-notes.wav"));

Console.WriteLine("\nTranscription:");
await using var audioResponse = audioSession.ProcessStreamingRequestAsync(audioRequest, ct);
await foreach (var item in audioResponse)
{
    using (item)
    {
        if (item is SpeechSegmentItem segment)
        {
            Console.Write(segment.Text);
            transcriptionText.Append(segment.Text);
        }
    }
}
using var finalTranscription = await audioResponse.FinalResponse;
Console.WriteLine();

// Unload the speech model to free memory
finalTranscription.Dispose();
await audioResponse.DisposeAsync();
audioRequest.Dispose();
audioSession.Dispose();
await speechModel.UnloadAsync();
// </transcription>

// <summarization>
// Load the chat model for summarization
var chatModel = await catalog.GetModelAsync("qwen2.5-0.5b")
    ?? throw new Exception("Chat model not found");

await chatModel.DownloadAsync(progress =>
{
    Console.Write($"\rDownloading chat model: {progress:F2}%");
    if (progress >= 100f) Console.WriteLine();
});

await chatModel.LoadAsync();
Console.WriteLine("Chat model loaded.");

// Summarize the transcription into organized notes.
using var chatSession = new ChatSession(chatModel);
using var chatRequest = new Request();
chatRequest.AddItem(MessageItem.System(
    "You are a note-taking assistant. Summarize the following transcription " +
    "into organized, concise notes with bullet points."));
chatRequest.AddItem(MessageItem.User(transcriptionText.ToString()));
using var chatResponse = await chatSession.ProcessRequestAsync(chatRequest, ct);
var summary = string.Concat(
    chatResponse.OfType<MessageItem>()
        .SelectMany(message => message.Parts)
        .OfType<TextItem>()
        .Where(text => text.Type == TextItemType.Default)
        .Select(text => text.Text));
Console.WriteLine($"\nSummary:\n{summary}");

// Clean up
chatResponse.Dispose();
chatRequest.Dispose();
chatSession.Dispose();
await chatModel.UnloadAsync();
Console.WriteLine("\nDone. Models unloaded.");
// </summarization>
// </complete_code>
