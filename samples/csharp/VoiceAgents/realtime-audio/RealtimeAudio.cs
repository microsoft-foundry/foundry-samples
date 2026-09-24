// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// This sample streams raw PCM16 24 kHz mono audio to a voice agent over a realtime
// connection and saves the streamed audio response. See realtime-text-and-tools for
// text input and a local function tool instead.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using OpenAI.Realtime;
using System.ClientModel;
using System.Text;

const int PcmSampleRate = 24_000;
const int PcmChannels = 1;
const int PcmBytesPerSample = sizeof(short);
const int InputChunkDurationMs = 100;
const int InputChunkSize = PcmSampleRate * PcmBytesPerSample * InputChunkDurationMs / 1000;
const int TrailingSilenceDurationMs = 1_000;

string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.");
string modelName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_MODEL")?.Trim() ?? "gpt-realtime";
string agentName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_NAME")?.Trim()
    ?? $"voice-audio-{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";
// The input file must contain raw PCM16 24 kHz mono audio with real, audible speech. Silence
// or non-speech noise will never trigger server-side turn detection. Defaults to the checked-in
// fixture (a few seconds of real speech) so this sample also runs unattended.
string audioInputPath = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_AUDIO_INPUT_FILE")?.Trim()
    ?? Path.Combine(AppContext.BaseDirectory, "assets", "input.pcm");
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

    // Force server-side turn detection to auto-create (and allow interrupting) a response once it
    // detects the end of speech. This sample streams a real recorded speech file rather than a live
    // microphone, so a manually triggered response could otherwise race with turn detection once it
    // recognizes speech partway through the stream, and the server would cancel one of the two.
    await session.ConfigureConversationSessionAsync(new RealtimeConversationSessionOptions
    {
        AudioOptions = new RealtimeConversationSessionAudioOptions
        {
            InputAudioOptions = new RealtimeConversationSessionInputAudioOptions
            {
                TurnDetection = new RealtimeServerVadTurnDetection
                {
                    CreateResponseEnabled = true,
                    InterruptResponseEnabled = true,
                    SilenceDuration = TimeSpan.FromMilliseconds(500),
                },
            },
        },
    });

    await session.AddItemAsync(RealtimeItem.CreateUserMessageItem("Say hello in one short sentence."));

    Console.WriteLine($"Streaming input audio from {audioInputPath} ...");
    long inputAudioBytes = 0;
    long outputAudioBytes = 0;
    string outputTranscript = string.Empty;
    using MemoryStream outputAudio = new();

    // Sending audio and receiving events run concurrently: turn detection can recognize speech
    // and start streaming a response before every input chunk (in particular, the trailing
    // silence below) has finished sending.
    await Task.WhenAll(SendInputAudioAsync(), ConsumeUpdatesAsync());

    Console.WriteLine($"\nOutput transcript: {outputTranscript}");
    Console.WriteLine($"Input audio:  {FormatAudioSize(inputAudioBytes)}");
    Console.WriteLine($"Output audio: {FormatAudioSize(outputAudioBytes)}");
    Console.WriteLine($"Total audio:  {FormatAudioSize(inputAudioBytes + outputAudioBytes)}");

    if (outputAudioBytes > 0)
    {
        WriteWavFile(audioOutputPath, outputAudio.ToArray());
        Console.WriteLine($"Saved response audio to: {audioOutputPath}");
    }

    async Task SendInputAudioAsync()
    {
        // Paced at roughly real-time (one chunk duration per chunk sent), like a live microphone
        // capture, so server-side turn detection sees speech arrive at a realistic cadence.
        await foreach (byte[] chunk in ReadPcmChunksAsync(audioInputPath, InputChunkSize))
        {
            await session.SendInputAudioAsync(BinaryData.FromBytes(chunk));
            inputAudioBytes += chunk.Length;
            await Task.Delay(InputChunkDurationMs);
        }

        // Turn detection needs a period of silence after real speech to recognize the turn has
        // ended; without this, it may never fire speech_stopped or auto-create a response.
        byte[] silenceChunk = new byte[InputChunkSize];
        for (int elapsedMs = 0; elapsedMs < TrailingSilenceDurationMs; elapsedMs += InputChunkDurationMs)
        {
            await session.SendInputAudioAsync(BinaryData.FromBytes(silenceChunk));
            inputAudioBytes += silenceChunk.Length;
            await Task.Delay(InputChunkDurationMs);
        }
    }

    async Task ConsumeUpdatesAsync()
    {
        await foreach (RealtimeServerUpdate update in session.ReceiveUpdatesAsync())
        {
            Console.WriteLine($"[event] {update.Kind}");
            switch (update)
            {
                case RealtimeServerUpdateResponseOutputAudioDelta audioDelta:
                    byte[] deltaBytes = audioDelta.Delta.ToArray();
                    outputAudio.Write(deltaBytes, 0, deltaBytes.Length);
                    outputAudioBytes += deltaBytes.Length;
                    break;
                case RealtimeServerUpdateResponseOutputAudioTranscriptDone transcriptDone:
                    outputTranscript = transcriptDone.Transcript;
                    break;
                case RealtimeServerUpdateError errorUpdate:
                    throw new InvalidOperationException($"{errorUpdate.Error.Code ?? "voice_agent_error"}: {errorUpdate.Error.Message}");
                case RealtimeServerUpdateResponseDone doneUpdate:
                    if (doneUpdate.Response.Status != RealtimeResponseStatus.Completed)
                    {
                        throw new InvalidOperationException($"Voice response ended with status: {doneUpdate.Response.Status}");
                    }
                    return;
            }
        }
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
            Instructions = "You are a helpful voice assistant. Keep answers to one short sentence.",
            Audio = new VoiceAgentAudioConfig
            {
                Input = new VoiceAgentAudioInputConfig { Format = new RealtimePcmAudioFormat { Rate = PcmSampleRate } },
            },
        };
        definition.OutputModalities.Add(VoiceOutputModality.Audio);
        await agentsClient.CreateAgentVersionAsync(agentName, new ProjectsAgentVersionCreationOptions(definition));
        return true;
    }
}

static string FormatAudioSize(long bytes)
{
    double seconds = bytes / (double)(PcmSampleRate * PcmBytesPerSample * PcmChannels);
    return $"{bytes} bytes ({bytes / 1024.0:F1} KB), {seconds:F2}s @ {PcmSampleRate} Hz / 16-bit / {PcmChannels}ch PCM";
}

static async IAsyncEnumerable<byte[]> ReadPcmChunksAsync(string path, int chunkSize)
{
    await using FileStream stream = File.OpenRead(path);
    byte[] buffer = new byte[chunkSize];
    int bytesRead;
    while ((bytesRead = await stream.ReadAsync(buffer)) > 0)
    {
        yield return bytesRead == chunkSize ? buffer : buffer[..bytesRead];
    }
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
