// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using Azure.AI.Projects;
using Azure.Identity;
using OpenAI.Realtime;
using System.ClientModel.Primitives;
using System.Text.Json;

const int MaxImageBytes = 8 * 1024 * 1024;
const string DefaultImagePrompt = "Describe this image briefly.";

if (args.Contains("--self-test"))
{
    await SelfTestAsync();
    return;
}

string projectEndpoint = RequiredEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
string agentName = RequiredEnvironmentVariable("FOUNDRY_VOICE_AGENT_NAME");
string imagePath = RequiredEnvironmentVariable("FOUNDRY_VOICE_AGENT_IMAGE_PATH");
string prompt = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_IMAGE_PROMPT")
    ?? DefaultImagePrompt;
BinaryData command = BuildImageCommand(imagePath, prompt);

AIProjectClient projectClient = new(
    new Uri(projectEndpoint),
    new DefaultAzureCredential());
using ProjectsRealtimeSessionClient session = (ProjectsRealtimeSessionClient)
    await projectClient.ProjectsRealtimeClient.StartSessionAsync(agentName, intent: null);

await SendImageTurnAsync(session, command);

await foreach (RealtimeServerUpdate update in session.ReceiveUpdatesAsync())
{
    switch (update)
    {
        case RealtimeServerUpdateResponseOutputTextDelta textDelta:
            Console.Write(textDelta.Delta);
            break;
        case RealtimeServerUpdateResponseOutputAudioTranscriptDelta transcriptDelta:
            Console.Write(transcriptDelta.Delta);
            break;
        case RealtimeServerUpdateError error:
            throw new InvalidOperationException(
                $"{error.Error.Code ?? "voice_agent_error"}: {error.Error.Message}");
        case RealtimeServerUpdateResponseDone done:
            if (done.Response.Status != RealtimeResponseStatus.Completed)
            {
                throw new InvalidOperationException(
                    $"Voice response ended with status: {done.Response.Status}");
            }
            return;
    }
}

static BinaryData BuildImageCommand(string imagePath, string prompt)
{
    FileInfo file = new(imagePath);
    if (file.Length > MaxImageBytes)
    {
        throw new ArgumentException("Choose an image no larger than 8 MiB.");
    }
    ValidateImage(imagePath, (int)file.Length);
    byte[] image = File.ReadAllBytes(imagePath);
    string mediaType = ValidateImage(imagePath, image.Length);
    return BuildImageCommandFromDataUrl(
        $"data:{mediaType};base64,{Convert.ToBase64String(image)}",
        prompt);
}

static string ValidateImage(string imagePath, int byteLength)
{
    string mediaType = Path.GetExtension(imagePath).ToLowerInvariant() switch
    {
        ".jpeg" or ".jpg" => "image/jpeg",
        ".png" => "image/png",
        ".webp" => "image/webp",
        _ => throw new ArgumentException("Choose a JPEG, PNG, or WebP image."),
    };
    if (byteLength == 0)
    {
        throw new ArgumentException("The image must not be empty.");
    }
    if (byteLength > MaxImageBytes)
    {
        throw new ArgumentException("Choose an image no larger than 8 MiB.");
    }
    return mediaType;
}

// The .NET realtime models don't yet expose an image content factory, so this
// sample uses the supported protocol-command overload.
// <image_turn>
static BinaryData BuildImageCommandFromDataUrl(string dataUrl, string prompt) =>
    BinaryData.FromObjectAsJson(new
    {
        type = "conversation.item.create",
        item = new
        {
            type = "message",
            role = "user",
            content = new object[]
            {
                new
                {
                    type = "input_text",
                    text = string.IsNullOrWhiteSpace(prompt)
                        ? DefaultImagePrompt
                        : prompt.Trim(),
                },
                new
                {
                    type = "input_image",
                    image_url = dataUrl,
                    detail = "low",
                },
            },
        },
    });

static async Task SendImageTurnAsync(
    ProjectsRealtimeSessionClient session,
    BinaryData command)
{
    await session.SendCommandAsync(command, new RequestOptions());
    await session.StartResponseAsync();
}
// </image_turn>

static async Task SendImageTurnForTestAsync(
    Func<BinaryData, Task> sendItem,
    Func<Task> requestResponse,
    BinaryData command)
{
    await sendItem(command);
    await requestResponse();
}

static async Task SelfTestAsync()
{
    BinaryData command = BuildImageCommandFromDataUrl(
        "data:image/png;base64,iVBORw==",
        "  ");
    int itemCount = 0;
    int responseCount = 0;
    await SendImageTurnForTestAsync(
        value =>
        {
            itemCount++;
            if (!ReferenceEquals(value, command))
            {
                throw new InvalidOperationException(
                    "The item command changed before send.");
            }
            return Task.CompletedTask;
        },
        () =>
        {
            responseCount++;
            return Task.CompletedTask;
        },
        command);

    using JsonDocument json = JsonDocument.Parse(command);
    JsonElement content = json.RootElement
        .GetProperty("item")
        .GetProperty("content");
    Assert(content.GetArrayLength() == 2);
    Assert(content[0].GetProperty("type").GetString() == "input_text");
    Assert(content[0].GetProperty("text").GetString() == DefaultImagePrompt);
    Assert(content[1].GetProperty("type").GetString() == "input_image");
    Assert(content[1].GetProperty("image_url").GetString()!
        .StartsWith("data:image/png;base64,", StringComparison.Ordinal));
    Assert(content[1].GetProperty("detail").GetString() == "low");
    Assert(itemCount == 1);
    Assert(responseCount == 1);
    Assert(ValidateImage("boundary.png", MaxImageBytes) == "image/png");
    AssertThrows(
        () => ValidateImage("oversize.png", MaxImageBytes + 1),
        "8 MiB");
    AssertThrows(
        () => ValidateImage("unsupported.gif", 1),
        "JPEG, PNG, or WebP");
    Console.WriteLine("Image payload validation passed.");
}

static void Assert(bool condition)
{
    if (!condition)
    {
        throw new InvalidOperationException("Image payload self-test failed.");
    }
}

static void AssertThrows(Action action, string expectedMessage)
{
    try
    {
        action();
    }
    catch (ArgumentException error)
        when (error.Message.Contains(expectedMessage, StringComparison.Ordinal))
    {
        return;
    }
    throw new InvalidOperationException("Expected validation to fail.");
}

static string RequiredEnvironmentVariable(string name)
{
    string? value = Environment.GetEnvironmentVariable(name)?.Trim();
    return string.IsNullOrEmpty(value)
        ? throw new InvalidOperationException(
            $"Set {name} before running the sample.")
        : value;
}
