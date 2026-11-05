// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text;
using System.Text.Json;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class SseFramingTests
{
    [TestCase("\n")]
    [TestCase("\r")]
    [TestCase("\r\n")]
    public async Task EveryByteSplit_PreservesNewlinesAndUtf8(string ending)
    {
        var raw = Encoding.UTF8.GetBytes(": heartbeat" + ending + ending +
            "data: {\"type\":\"token\",\"content\":\"你好 👋\"}" + ending + ending +
            "data: {\"type\":\"done\",\"full_text\":\"你好 👋\"}" + ending + ending);
        for (var split = 0; split <= raw.Length; split++)
        {
            var events = await Parse(raw[..split], Array.Empty<byte>(), raw[split..]);
            Assert.That(events.Count, Is.EqualTo(2));
            Assert.That(events[0].GetProperty("content").GetString(), Is.EqualTo("你好 👋"));
        }
        Assert.That((await Parse(raw.Select(value => new[] { value }).ToArray())).Count, Is.EqualTo(2));
    }

    [Test]
    public async Task MixedLineEndings_AndMultilineData_AreAccepted()
    {
        var raw = Encoding.UTF8.GetBytes("data: {\"type\":\"token\",\rdata: \"content\":\"ok\"}\n\r\n");
        var events = await Parse(raw.Select(value => new[] { value }).ToArray());
        Assert.That(events.Single().GetProperty("content").GetString(), Is.EqualTo("ok"));
    }

    [TestCase("\n", -1)]
    [TestCase("\n", 0)]
    [TestCase("\n", 1)]
    [TestCase("\r", -1)]
    [TestCase("\r", 0)]
    [TestCase("\r", 1)]
    [TestCase("\r\n", -1)]
    [TestCase("\r\n", 0)]
    [TestCase("\r\n", 1)]
    public async Task FrameBudget_IsIndependentOfDelimiterPartitions(string ending, int extra)
    {
        const int cap = 65_536;
        var empty = "data: " + JsonSerializer.Serialize(new { type = "token", content = "ok", pad = "" });
        var frame = "data: " + JsonSerializer.Serialize(new
        {
            type = "token",
            content = "ok",
            pad = new string('x', cap + extra - empty.Length),
        });
        Assert.That(frame.Length, Is.EqualTo(cap + extra));
        var raw = Encoding.UTF8.GetBytes(frame + ending + ending);
        for (var split = frame.Length - 1; split <= raw.Length; split++)
        {
            var left = raw[..split];
            var right = raw[split..];
            if (extra > 0)
            {
                Assert.ThrowsAsync<InvalidOperationException>(async () => await Parse(left, right));
            }
            else
            {
                Assert.That((await Parse(left, right)).Count, Is.EqualTo(1));
            }
        }
    }

    [Test]
    public async Task OneLeadingUtf8Bom_IsIgnoredEvenWhenSplitIntoBytes()
    {
        var raw = Encoding.UTF8.GetBytes("\uFEFFdata: {\"type\":\"token\",\"content\":\"\uFEFF你好 👋\"}\n\n");
        for (var split = 0; split <= raw.Length; split++)
        {
            var events = await Parse(raw[..split], Array.Empty<byte>(), raw[split..]);
            Assert.That(events.Single().GetProperty("content").GetString(), Is.EqualTo("\uFEFF你好 👋"));
        }
        Assert.That((await Parse(raw.Select(value => new[] { value }).ToArray())).Count, Is.EqualTo(1));
        Assert.That(await Parse(Encoding.UTF8.GetBytes("\uFEFF"), raw), Is.Empty);
    }

    private static async Task<List<JsonElement>> Parse(params byte[][] chunks)
    {
        await using var stream = new FragmentedStream(chunks);
        var events = new List<JsonElement>();
        await foreach (var item in InvocationAdapter.ReadEventsAsync(stream, CancellationToken.None))
        {
            events.Add(item);
        }
        return events;
    }

    private sealed class FragmentedStream(IEnumerable<byte[]> chunks) : Stream
    {
        private readonly Queue<byte[]> _chunks = new(chunks.Where(chunk => chunk.Length != 0));
        private int _offset;
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position
        {
            get => throw new NotSupportedException();
            set => throw new NotSupportedException();
        }
        public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));
        public override int Read(Span<byte> buffer)
        {
            if (_chunks.Count == 0) { return 0; }
            var current = _chunks.Peek();
            var count = Math.Min(buffer.Length, current.Length - _offset);
            current.AsSpan(_offset, count).CopyTo(buffer);
            _offset += count;
            if (_offset == current.Length) { _chunks.Dequeue(); _offset = 0; }
            return count;
        }
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return ValueTask.FromResult(Read(buffer.Span));
        }
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}
