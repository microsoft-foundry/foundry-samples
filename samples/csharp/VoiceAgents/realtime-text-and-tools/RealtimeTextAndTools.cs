// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// This sample sends text to a voice agent, streams its text/audio response, and handles a
// local function tool call: the agent requests a call to get_current_weather, this sample
// supplies a mocked result, and the agent completes a follow-up response using that result.
// See realtime-audio for streaming PCM audio input instead of text.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using OpenAI;
using OpenAI.Realtime;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Text;
using System.Text.Json;

const int PcmSampleRate = 24_000;
const int PcmChannels = 1;
const int PcmBytesPerSample = sizeof(short);

string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.");
string modelName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_MODEL")?.Trim() ?? "gpt-realtime";
string agentName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_NAME")?.Trim()
    ?? $"voice-text-{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";
string audioOutputPath = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_AUDIO_OUTPUT_FILE")?.Trim()
    ?? Path.Combine(AppContext.BaseDirectory, "output.wav");

AIProjectClient projectClient = new(new Uri(projectEndpoint), new DefaultAzureCredential());
AgentAdministrationClient agentsClient = projectClient.AgentAdministrationClient;
bool created = await EnsureVoiceAgentAsync();

try
{
    Console.WriteLine("Connecting realtime session...");
    using ProjectsRealtimeSessionClient session = (ProjectsRealtimeSessionClient)
        await projectClient.ProjectsRealtimeClient.StartSessionAsync(agentName, intent: null);
    Console.WriteLine("Connected!\n");

    await session.AddItemAsync(RealtimeItem.CreateUserMessageItem("What is the weather in Seattle? Use the weather tool."));
    await session.StartResponseAsync();

    int toolCallCount = 0;
    long textCharacterCount = 0;
    long outputAudioBytes = 0;
    bool pendingToolOutput = false;
    using MemoryStream outputAudio = new();

    await foreach (RealtimeServerUpdate update in session.ReceiveUpdatesAsync())
    {
        Console.WriteLine($"[event] {update.Kind}{DescribeEvent(update)}");
        switch (update)
        {
            case RealtimeServerUpdateResponseOutputTextDelta textDelta:
                textCharacterCount += textDelta.Delta.Length;
                Console.Write(textDelta.Delta);
                break;
            case RealtimeServerUpdateResponseOutputAudioTranscriptDelta transcriptDelta:
                textCharacterCount += transcriptDelta.Delta.Length;
                Console.Write(transcriptDelta.Delta);
                break;
            case RealtimeServerUpdateResponseOutputAudioDelta audioDelta:
                byte[] deltaBytes = audioDelta.Delta.ToArray();
                outputAudio.Write(deltaBytes, 0, deltaBytes.Length);
                outputAudioBytes += deltaBytes.Length;
                break;
            case RealtimeServerUpdateResponseFunctionCallArgumentsDone functionCallDone:
                toolCallCount++;
                pendingToolOutput = true;
                // The voice agent may call the tool with the "city" argument omitted even though it
                // is declared as required; fall back to the city named in the prompt above so the
                // mocked weather result stays meaningful regardless.
                string city = ExtractCity(functionCallDone.FunctionArguments.ToString(), fallback: "Seattle");
                string toolResult = JsonSerializer.Serialize(new { city, temperature = 62, unit = "F" });
                Console.WriteLine($"  tool call: {functionCallDone.FunctionName}({functionCallDone.FunctionArguments}) -> {toolResult}");
                await session.AddItemAsync(RealtimeItem.CreateFunctionCallOutputItem(functionCallDone.CallId, toolResult));
                break;
            case RealtimeServerUpdateError errorUpdate:
                throw new InvalidOperationException($"{errorUpdate.Error.Code ?? "voice_agent_error"}: {errorUpdate.Error.Message}");
            case RealtimeServerUpdateResponseDone:
                if (pendingToolOutput)
                {
                    pendingToolOutput = false;
                    await session.StartResponseAsync();
                }
                else
                {
                    goto Done;
                }
                break;
        }
    }

Done:
    Console.WriteLine($"\n\nCompleted with {toolCallCount} tool call(s), {textCharacterCount} text character(s).");
    Console.WriteLine("Input audio:  N/A (this sample sends text input only).");
    Console.WriteLine($"Output audio: {FormatAudioSize(outputAudioBytes)}");

    if (outputAudioBytes > 0)
    {
        WriteWavFile(audioOutputPath, outputAudio.ToArray());
        Console.WriteLine($"Saved response audio to: {audioOutputPath}");
    }
}
finally
{
    if (created)
    {
        Console.WriteLine("\nDeleting the sample agent...");
        ClientResult deleteResult = await agentsClient.DeleteAgentAsync(agentName);
        Console.WriteLine($"[REST] DELETE agent -> {(int)deleteResult.GetRawResponse().Status}");
    }
}

async Task<bool> EnsureVoiceAgentAsync()
{
    try
    {
        await agentsClient.GetAgentAsync(agentName);
        return false;
    }
    catch (ClientResultException ex) when (ex.Status == 404)
    {
        VoiceAgentDefinition definition = new()
        {
            ModelType = VoiceModelType.SelfDeployed,
            Model = modelName,
            Instructions = "You are a helpful voice assistant. Use tools when appropriate.",
        };
        definition.OutputModalities.Add(VoiceOutputModality.Text);
        definition.OutputModalities.Add(VoiceOutputModality.Audio);
        definition.Tools.Add(new VoiceAgentFunctionTool("get_current_weather")
        {
            Description = "Get the current weather for a city.",
            Parameters = ModelReaderWriter.Read<RealtimeFunctionToolParameters>(BinaryData.FromObjectAsJson(new
            {
                type = "object",
                properties = new { city = new { type = "string" } },
                required = new[] { "city" },
            })),
        });
        await agentsClient.CreateAgentVersionAsync(agentName, new ProjectsAgentVersionCreationOptions(definition));
        return true;
    }
}

static string ExtractCity(string argumentsJson, string fallback)
{
    using JsonDocument doc = JsonDocument.Parse(argumentsJson);
    return doc.RootElement.TryGetProperty("city", out JsonElement city) ? city.GetString() ?? fallback : fallback;
}

static string DescribeEvent(RealtimeServerUpdate update) => update switch
{
    RealtimeServerUpdateResponseOutputAudioDelta audioDelta => $" ({audioDelta.Delta.ToArray().Length} bytes)",
    RealtimeServerUpdateResponseOutputTextDelta textDelta => $" ({textDelta.Delta.Length} chars)",
    RealtimeServerUpdateResponseOutputAudioTranscriptDelta transcriptDelta => $" ({transcriptDelta.Delta.Length} chars)",
    RealtimeServerUpdateResponseFunctionCallArgumentsDone functionCallDone =>
        $" (call_id={functionCallDone.CallId}, name={functionCallDone.FunctionName})",
    RealtimeServerUpdateResponseDone doneUpdate => $" (status={doneUpdate.Response.Status})",
    _ => string.Empty,
};

static string FormatAudioSize(long bytes)
{
    double seconds = bytes / (double)(PcmSampleRate * PcmBytesPerSample * PcmChannels);
    return $"{bytes} bytes ({bytes / 1024.0:F1} KB), {seconds:F2}s @ {PcmSampleRate} Hz / 16-bit / {PcmChannels}ch PCM";
}

static void WriteWavFile(string path, byte[] pcmData)
{
    using FileStream stream = File.Create(path);
    using BinaryWriter writer = new(stream);
    int byteRate = PcmSampleRate * PcmChannels * PcmBytesPerSample;
    writer.Write(Encoding.ASCII.GetBytes("RIFF"));
    writer.Write(36 + pcmData.Length);
    writer.Write(Encoding.ASCII.GetBytes("WAVE"));
    writer.Write(Encoding.ASCII.GetBytes("fmt "));
    writer.Write(16);
    writer.Write((short)1); // PCM
    writer.Write((short)PcmChannels);
    writer.Write(PcmSampleRate);
    writer.Write(byteRate);
    writer.Write((short)(PcmChannels * PcmBytesPerSample));
    writer.Write((short)(PcmBytesPerSample * 8));
    writer.Write(Encoding.ASCII.GetBytes("data"));
    writer.Write(pcmData.Length);
    writer.Write(pcmData);
}
