// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text;
using System.Text.Json;
using CopilotSample;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.Testing;
using Microsoft.Agents.Core.Models;
using NUnit.Framework;

namespace ActivitySamples.Tests;

[TestFixture]
public sealed class FileTransferTests
{
    private string _root = null!;
    private TaskStore _store = null!;

    [SetUp]
    public void SetUp()
    {
        _root = Path.Combine(Path.GetTempPath(), "activity-file-tests", Guid.NewGuid().ToString("N"));
        _store = new TaskStore(_root);
    }

    [TearDown]
    public void TearDown()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    [TestCase("http://tenant.sharepoint.com/file")]
    [TestCase("https://tenant.sharepoint.com.evil.example/file")]
    [TestCase("https://127.0.0.1/file")]
    [TestCase("https://user@tenant.sharepoint.com/file")]
    [TestCase("https://tenant.sharepoint.com:8443/file")]
    [TestCase("file:///C:/test.txt")]
    public void FileUrlsRejectUntrustedDestinations(string url) =>
        Assert.Throws<ArgumentException>(() => FileTransfers.RequireMicrosoftFileUrl(url));

    [TestCase("https://tenant.sharepoint.com/file")]
    [TestCase("https://upload.up.1drv.com/file")]
    [TestCase("https://tenant-my.sharepoint.com/file")]
    public void FileUrlsAllowMicrosoftFileServices(string url) =>
        Assert.That(FileTransfers.RequireMicrosoftFileUrl(url).Scheme, Is.EqualTo("https"));

    [Test]
    public void GeneratedFilesAreLimitedToTheConversationDirectory()
    {
        var first = _store.Workspace("one");
        var path = Path.Combine(_store.Workspace("two"), "private.txt");
        File.WriteAllText(path, "private");
        Assert.Throws<ArgumentException>(() => FileTransfers.RequireWorkspaceFile(first, path));
    }

    [Test]
    public void EmptyAndOversizedGeneratedFilesAreRejected()
    {
        var workspace = _store.Workspace("one");
        var path = Path.Combine(workspace, "file.txt");
        File.WriteAllBytes(path, []);
        Assert.Throws<ArgumentException>(() => FileTransfers.RequireWorkspaceFile(workspace, path));
        File.WriteAllBytes(path, new byte[FileTransfers.MaximumFileBytes + 1]);
        Assert.Throws<ArgumentException>(() => FileTransfers.RequireWorkspaceFile(workspace, path));
    }

    [Test]
    public async Task SharedFileBytesArePassedToTheModelWithoutExtraction()
    {
        using var http = new HttpClient(new RecordingHandler("raw document bytes"u8.ToArray()));
        var files = new FileTransfers(http, _store);
        using var context = new TurnContext(new TestAdapter(), new Activity
        {
            Type = ActivityTypes.Message,
            Attachments = [new Attachment
            {
                ContentType = "application/vnd.microsoft.teams.file.download.info",
                Name = "../../report.txt",
                Content = new { downloadUrl = "https://tenant.sharepoint.com/file" }
            }]
        });
        var attachments = await files.DownloadAsync(context, "one", CancellationToken.None);
        var file = attachments.Single() as GitHub.Copilot.AttachmentFile;
        Assert.That(file, Is.Not.Null);
        Assert.That(await File.ReadAllTextAsync(file!.Path), Is.EqualTo("raw document bytes"));
        Assert.That(Path.GetDirectoryName(file.Path), Is.EqualTo(Path.Combine(_store.Workspace("one"), "shared")));
    }

    [Test]
    public void OversizedSharedFileFailsExplicitly()
    {
        using var http = new HttpClient(new RecordingHandler(new byte[FileTransfers.MaximumFileBytes + 1]));
        var files = new FileTransfers(http, _store);
        using var context = new TurnContext(new TestAdapter(), new Activity
        {
            Attachments = [new Attachment { Content = new { downloadUrl = "https://tenant.sharepoint.com/file" } }]
        });
        Assert.ThrowsAsync<InvalidDataException>(() => files.DownloadAsync(context, "one", CancellationToken.None));
    }

    [TestCase(240, ".txt")]
    [TestCase(240, "")]
    [TestCase(1, ".abcdefghijklmnopqrstuvwxyz")]
    public async Task LongSharedFilenamesUseBoundedDiskNamesAndPreserveDisplayNames(int stemLength, string extension)
    {
        var name = new string('a', stemLength) + extension;
        using var http = new HttpClient(new RecordingHandler("file bytes"u8.ToArray()));
        var files = new FileTransfers(http, _store);
        using var context = new TurnContext(new TestAdapter(), new Activity
        {
            Attachments = [new Attachment
            {
                Name = name,
                ContentType = "application/vnd.microsoft.teams.file.download.info",
                Content = new { downloadUrl = "https://tenant.sharepoint.com/file" }
            }]
        });
        var attachments = await files.DownloadAsync(context, "one", CancellationToken.None);
        var file = (GitHub.Copilot.AttachmentFile)attachments.Single();
        Assert.That(file.DisplayName, Is.EqualTo(name));
        Assert.That(Path.GetFileName(file.Path).Length, Is.LessThanOrEqualTo(48));
        Assert.That(await File.ReadAllTextAsync(file.Path), Is.EqualTo("file bytes"));
        if (extension.Length <= 16)
        {
            Assert.That(Path.GetExtension(file.Path), Is.EqualTo(extension));
        }
    }

    [Test]
    public async Task ConsentUploadUsesStoredBytesAndReturnsFileInfoCard()
    {
        var handler = new RecordingHandler([]);
        using var http = new HttpClient(handler);
        var files = new FileTransfers(http, _store);
        var path = Path.Combine(_store.Workspace("one"), "report.txt");
        await File.WriteAllTextAsync(path, "generated bytes");
        var consent = await files.CreateConsentAsync("one", path, CancellationToken.None);
        var content = JsonSerializer.SerializeToElement(consent.Content);
        Assert.That(content.TryGetProperty("b64", out _), Is.False);
        var token = content.GetProperty("acceptContext").GetProperty("token").GetString();
        var adapter = new TestAdapter();
        using var context = new TurnContext(adapter, new Activity
        {
            Type = ActivityTypes.Invoke, Name = "fileConsent/invoke",
            Conversation = new ConversationAccount { Id = "one" },
            Value = new
            {
                action = "accept", context = new { token },
                uploadInfo = new
                {
                    uploadUrl = "https://upload.up.1drv.com/file",
                    contentUrl = "https://tenant.sharepoint.com/report.txt",
                    uniqueId = "file-id"
                }
            }
        });
        await files.HandleConsentAsync(context, "one", CancellationToken.None);
        Assert.That(handler.Method, Is.EqualTo(HttpMethod.Put));
        Assert.That(Encoding.UTF8.GetString(handler.Uploaded!), Is.EqualTo("generated bytes"));
        Assert.That(handler.ContentRange, Is.EqualTo("bytes 0-14/15"));
        var reply = await adapter.GetNextReplyAsync();
        Assert.That(reply.Attachments.Single().ContentType, Is.EqualTo("application/vnd.microsoft.teams.card.file.info"));
        Assert.That(Directory.GetFiles(Path.Combine(_store.Workspace("one"), "pending")), Is.Empty);
    }

    [Test]
    public async Task ConsentCannotReadAnotherConversationsFile()
    {
        using var http = new HttpClient(new RecordingHandler([]));
        var files = new FileTransfers(http, _store);
        var path = Path.Combine(_store.Workspace("one"), "report.txt");
        await File.WriteAllTextAsync(path, "private");
        var consent = await files.CreateConsentAsync("one", path, CancellationToken.None);
        var token = JsonSerializer.SerializeToElement(consent.Content).GetProperty("acceptContext").GetProperty("token").GetString();
        using var context = new TurnContext(new TestAdapter(), new Activity
        {
            Value = new { action = "accept", context = new { token } }
        });
        Assert.ThrowsAsync<DirectoryNotFoundException>(() => files.HandleConsentAsync(context, "two", CancellationToken.None));
    }

    private sealed class RecordingHandler(byte[] response) : HttpMessageHandler
    {
        public HttpMethod? Method { get; private set; }
        public byte[]? Uploaded { get; private set; }
        public string? ContentRange { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Method = request.Method;
            if (request.Content is not null)
            {
                Uploaded = await request.Content.ReadAsByteArrayAsync(cancellationToken);
                ContentRange = request.Content.Headers.ContentRange?.ToString();
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(response) };
        }
    }
}
