// Live Audio Transcription — Foundry Local SDK v2 Example
//
// NAudio's WaveInEvent is Windows-only. On non-Windows platforms, the sample
// falls back to synthetic PCM audio.

using Microsoft.AI.Foundry.Local;
#if WINDOWS
using NAudio.Wave;
#endif

Console.WriteLine("===========================================================");
Console.WriteLine("   Foundry Local -- Live Audio Transcription Demo");
Console.WriteLine("===========================================================");
Console.WriteLine();

var config = new Configuration
{
    AppName = "foundry_local_samples",
    LogLevel = Microsoft.AI.Foundry.Local.LogLevel.Information
};

await FoundryLocalManager.CreateAsync(config, Utils.GetAppLogger());
var mgr = FoundryLocalManager.Instance;

await Utils.RunWithSpinner("Registering execution providers", mgr.DownloadAndRegisterEpsAsync());

var catalog = await mgr.GetCatalogAsync();

// English-only:
var modelAlias = "nemotron-speech-streaming-en-0.6b";
// Multi-lingual (supports 30+ languages including auto-detect):
// var modelAlias = "nvidia-nemotron-3.5-asr-streaming-multilingual-0.6b";

var model = await catalog.GetModelAsync(modelAlias)
    ?? throw new Exception($"Model \"{modelAlias}\" not found in catalog");

await model.DownloadAsync(progress =>
{
    Console.Write($"\rDownloading model: {progress:F2}%");
    if (progress >= 100f)
    {
        Console.WriteLine();
    }
});

Console.Write($"Loading model {model.Id}...");
await model.LoadAsync();
Console.WriteLine("done.");

using (var audioSession = new AudioSession(model))
using (var inputQueue = new ItemQueue())
using (var request = new Request())
{
    audioSession.SetOptions(new RequestOptions
    {
        AdditionalOptions = new Dictionary<string, string> { ["language"] = "en" }
    });
    audioSession.SetStreaming(true);

    request.AddItem(AudioItem.CreateFormatDescriptor("pcm", 16000, 1));
    request.AddItem(inputQueue, takeOwnership: false);

    await using var stream = audioSession.ProcessStreamingRequestAsync(request);
    var producer = Task.Run(() => ProduceAudioAsync(inputQueue, args.Contains("--synth")));

    await foreach (var item in stream)
    {
        using (item)
        {
            if (item is SpeechSegmentItem segment)
            {
                if (segment.Kind == SpeechSegmentKind.Final)
                {
                    Console.WriteLine();
                    Console.WriteLine($"  [FINAL] {segment.Text}");
                }
                else if (!string.IsNullOrEmpty(segment.Text))
                {
                    Console.ForegroundColor = ConsoleColor.Cyan;
                    Console.Write(segment.Text);
                    Console.ResetColor();
                }
                Console.Out.Flush();
            }
        }
    }

    await producer;
    using var finalResponse = await stream.FinalResponse;
    var transcript = finalResponse.OfType<SpeechResultItem>().FirstOrDefault()?.Text;
    if (!string.IsNullOrWhiteSpace(transcript))
    {
        Console.WriteLine($"\nTranscript: {transcript}");
    }
}

await model.UnloadAsync();

static async Task ProduceAudioAsync(ItemQueue inputQueue, bool useSynth)
{
    try
    {
        if (!useSynth && OperatingSystem.IsWindows())
        {
            await CaptureMicrophoneAsync(inputQueue);
        }
        else
        {
            if (!OperatingSystem.IsWindows() && !useSynth)
            {
                Console.WriteLine("NAudio mic capture is Windows-only. Falling back to synthetic audio...");
            }
            await PushSyntheticAudioAsync(inputQueue);
        }
    }
    finally
    {
        inputQueue.MarkFinished();
    }
}

static async Task CaptureMicrophoneAsync(ItemQueue inputQueue)
{
#if WINDOWS
    using var waveIn = new WaveIn
    {
        WaveFormat = new WaveFormat(rate: 16000, bits: 16, channels: 1),
        BufferMilliseconds = 100
    };

    var audioChannel = System.Threading.Channels.Channel.CreateBounded<byte[]>(
        new System.Threading.Channels.BoundedChannelOptions(50)
        {
            FullMode = System.Threading.Channels.BoundedChannelFullMode.DropOldest
        });

    waveIn.DataAvailable += (_, e) =>
    {
        if (e.BytesRecorded > 0)
        {
            var buffer = new byte[e.BytesRecorded];
            Buffer.BlockCopy(e.Buffer, 0, buffer, 0, e.BytesRecorded);
            audioChannel.Writer.TryWrite(buffer);
        }
    };

    Console.WriteLine();
    Console.WriteLine("===========================================================");
    Console.WriteLine("  LIVE TRANSCRIPTION ACTIVE");
    Console.WriteLine("  Speak into your microphone.");
    Console.WriteLine("  Transcription appears in real-time (cyan text).");
    Console.WriteLine("  Press ENTER to stop recording.");
    Console.WriteLine("===========================================================");
    Console.WriteLine();

    waveIn.StartRecording();
    var pushTask = Task.Run(async () =>
    {
        await foreach (var chunk in audioChannel.Reader.ReadAllAsync())
        {
            inputQueue.Push(BytesItem.CreateOwned(chunk));
        }
    });

    Console.ReadLine();
    waveIn.StopRecording();
    audioChannel.Writer.Complete();
    await pushTask;
#else
    await Task.CompletedTask;
    throw new PlatformNotSupportedException("Microphone capture requires Windows.");
#endif
}

static async Task PushSyntheticAudioAsync(ItemQueue inputQueue)
{
    Console.WriteLine("Pushing synthetic audio (440Hz sine, 2s)...");
    const int sampleRate = 16000;
    const int duration = 2;
    var totalSamples = sampleRate * duration;
    var pcmBytes = new byte[totalSamples * 2];
    for (var i = 0; i < totalSamples; i++)
    {
        var t = (double)i / sampleRate;
        var sample = (short)(short.MaxValue * 0.5 * Math.Sin(2 * Math.PI * 440 * t));
        pcmBytes[i * 2] = (byte)(sample & 0xFF);
        pcmBytes[i * 2 + 1] = (byte)((sample >> 8) & 0xFF);
    }

    var chunkSize = (sampleRate / 10) * 2;
    for (var offset = 0; offset < pcmBytes.Length; offset += chunkSize)
    {
        var length = Math.Min(chunkSize, pcmBytes.Length - offset);
        inputQueue.Push(BytesItem.CreateOwned(pcmBytes.AsMemory(offset, length)));
        await Task.Delay(100);
    }

    Console.WriteLine("✓ Synthetic audio pushed");
}
