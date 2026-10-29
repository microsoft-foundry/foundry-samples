// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

namespace VoiceHostedAgent;

internal sealed record ResponsePlan(
    IAsyncEnumerable<string> Chunks,
    bool Streaming,
    BinaryData? Voice)
{
    internal static ResponsePlan Fixed(
        string text,
        bool streaming = false,
        BinaryData? voice = null) =>
        new(FixedChunks(text), streaming, voice);

    private static async IAsyncEnumerable<string> FixedChunks(string text)
    {
        await Task.Yield();
        yield return text;
    }
}
