// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.RegularExpressions;
using GitHub.Copilot;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Connector;
using Microsoft.Agents.Core.Models;
using Attachment = Microsoft.Agents.Core.Models.Attachment;

namespace CopilotSample;

public sealed class FileTransfers(HttpClient http, TaskStore store)
{
    public const int MaximumFileBytes = 4 * 1024 * 1024;
    public const string ConsentContentType = "application/vnd.microsoft.teams.card.file.consent";
    private sealed record PendingFile(string Name, string Data, DateTimeOffset CreatedAt);

    public async Task<IList<GitHub.Copilot.Attachment>> DownloadAsync(
        ITurnContext context, string conversationId, CancellationToken cancellationToken)
    {
        var result = new List<GitHub.Copilot.Attachment>();
        foreach (var attachment in context.Activity.Attachments ?? [])
        {
            var content = JsonSerializer.SerializeToElement(attachment.Content);
            byte[] data;
            var name = Path.GetFileName(attachment.Name ?? "attachment");
            if (content.ValueKind == JsonValueKind.Object
                && content.TryGetProperty("downloadUrl", out var downloadUrl))
            {
                var uri = RequireMicrosoftFileUrl(downloadUrl.GetString() ?? "");
                using var response = await http.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
                response.EnsureSuccessStatusCode();
                await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
                data = await ReadLimitedAsync(stream, cancellationToken);
            }
            else if (attachment.ContentType?.StartsWith("image/", StringComparison.OrdinalIgnoreCase) == true)
            {
                var reference = Regex.Match(attachment.ContentUrl ?? "", @"/v3/attachments/([^/]+)/views/([^/?]+)");
                if (!reference.Success)
                {
                    throw new InvalidDataException("The image does not have a supported Bot Connector attachment URL.");
                }
                var connector = context.Services.Get<IConnectorClient>()
                    ?? throw new InvalidOperationException("No authenticated Bot Connector is available to read this image.");
                await using var stream = await connector.Attachments.GetAttachmentAsync(
                    reference.Groups[1].Value, reference.Groups[2].Value, cancellationToken);
                data = await ReadLimitedAsync(stream, cancellationToken);
            }
            else
            {
                continue;
            }

            if (attachment.ContentType?.StartsWith("image/", StringComparison.OrdinalIgnoreCase) == true)
            {
                result.Add(new AttachmentBlob
                {
                    Data = Convert.ToBase64String(data), MimeType = attachment.ContentType, DisplayName = name
                });
            }
            else
            {
                var directory = Path.Combine(store.Workspace(conversationId), "shared");
                Directory.CreateDirectory(directory);
                if (string.IsNullOrEmpty(name) || name is "." or "..")
                {
                    name = "attachment";
                }
                var extension = Path.GetExtension(name);
                if (extension.Length > 16 || !Regex.IsMatch(extension, @"^\.[A-Za-z0-9]+$"))
                {
                    extension = "";
                }
                var path = Path.Combine(directory, $"{Guid.NewGuid():N}{extension}");
                await File.WriteAllBytesAsync(path, data, cancellationToken);
                result.Add(new AttachmentFile { Path = path, DisplayName = name });
            }
        }
        return result;
    }

    public async Task<Attachment> CreateConsentAsync(string conversationId, string path, CancellationToken cancellationToken)
    {
        path = RequireWorkspaceFile(store.Workspace(conversationId), path);
        var data = await File.ReadAllBytesAsync(path, cancellationToken);
        var token = Guid.NewGuid().ToString("N");
        var pendingDirectory = Path.Combine(store.Workspace(conversationId), "pending");
        Directory.CreateDirectory(pendingDirectory);
        var name = Path.GetFileName(path);
        await File.WriteAllTextAsync(Path.Combine(pendingDirectory, token + ".json"),
            JsonSerializer.Serialize(new PendingFile(name, Convert.ToBase64String(data), DateTimeOffset.UtcNow)), cancellationToken);
        return new Attachment
        {
            ContentType = ConsentContentType,
            Name = name,
            Content = new
            {
                description = $"Generated document: {name}",
                sizeInBytes = data.Length,
                acceptContext = new { token },
                declineContext = new { token }
            }
        };
    }

    public async Task HandleConsentAsync(ITurnContext context, string conversationId, CancellationToken cancellationToken)
    {
        var value = JsonSerializer.SerializeToElement(context.Activity.Value);
        var action = value.GetProperty("action").GetString();
        var token = value.GetProperty("context").GetProperty("token").GetString();
        if (!Guid.TryParseExact(token, "N", out _))
        {
            throw new InvalidDataException("The file consent token is invalid.");
        }
        var path = Path.Combine(store.Workspace(conversationId), "pending", token + ".json");
        if (action == "decline")
        {
            File.Delete(path);
            await context.SendActivityAsync("No problem - I won't send the file.", cancellationToken: cancellationToken);
            return;
        }
        if (action != "accept")
        {
            throw new InvalidDataException("The file consent action is not supported.");
        }
        var pending = JsonSerializer.Deserialize<PendingFile>(await File.ReadAllTextAsync(path, cancellationToken))
            ?? throw new InvalidDataException("The pending file record is invalid.");
        if (DateTimeOffset.UtcNow - pending.CreatedAt > TimeSpan.FromHours(1))
        {
            File.Delete(path);
            throw new InvalidOperationException("The file offer expired. Ask the assistant to generate the file again.");
        }
        var upload = value.GetProperty("uploadInfo");
        var uri = RequireMicrosoftFileUrl(upload.GetProperty("uploadUrl").GetString() ?? "");
        var bytes = Convert.FromBase64String(pending.Data);
        using var request = new HttpRequestMessage(HttpMethod.Put, uri) { Content = new ByteArrayContent(bytes) };
        request.Content.Headers.ContentRange = new(0, bytes.Length - 1, bytes.Length);
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        await context.SendActivityAsync(new Activity
        {
            Type = ActivityTypes.Message,
            Attachments = [new Attachment
            {
                ContentType = "application/vnd.microsoft.teams.card.file.info",
                ContentUrl = RequireMicrosoftFileUrl(upload.GetProperty("contentUrl").GetString() ?? "").AbsoluteUri,
                Name = pending.Name,
                Content = new { uniqueId = upload.GetProperty("uniqueId").GetString(), fileType = Path.GetExtension(pending.Name).TrimStart('.') }
            }]
        }, cancellationToken);
        File.Delete(path);
    }

    public static string RequireWorkspaceFile(string workspace, string path)
    {
        var root = Path.GetFullPath(workspace) + Path.DirectorySeparatorChar;
        var fullPath = Path.GetFullPath(path, workspace);
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (!fullPath.StartsWith(root, comparison))
        {
            throw new ArgumentException("Files must be inside this conversation's working directory.", nameof(path));
        }
        for (var entry = new FileInfo(fullPath); entry is not null;)
        {
            if ((entry.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new ArgumentException("Symbolic links are not supported for file delivery.", nameof(path));
            }
            var parent = entry.Directory;
            if (parent is null || parent.FullName.Equals(Path.GetFullPath(workspace), comparison))
            {
                break;
            }
            entry = new FileInfo(parent.FullName);
        }
        var info = new FileInfo(fullPath);
        if (!info.Exists || info.Length is 0 or > MaximumFileBytes)
        {
            throw new ArgumentException("The file must exist and contain between 1 byte and 4 MiB.", nameof(path));
        }
        return fullPath;
    }

    public static Uri RequireMicrosoftFileUrl(string value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri)
            || uri.Scheme != Uri.UriSchemeHttps || !uri.IsDefaultPort || !string.IsNullOrEmpty(uri.UserInfo)
            || !new[] { "sharepoint.com", "1drv.com", "onedrive.com" }.Any(
                suffix => uri.Host.EndsWith("." + suffix, StringComparison.OrdinalIgnoreCase)))
        {
            throw new ArgumentException("File transfers require an HTTPS SharePoint or OneDrive URL.", nameof(value));
        }
        return uri;
    }

    private static async Task<byte[]> ReadLimitedAsync(Stream stream, CancellationToken cancellationToken)
    {
        using var output = new MemoryStream();
        var buffer = new byte[81920];
        int count;
        while ((count = await stream.ReadAsync(buffer, cancellationToken)) > 0)
        {
            if (output.Length + count > MaximumFileBytes)
            {
                throw new InvalidDataException("Shared files must not exceed 4 MiB.");
            }
            await output.WriteAsync(buffer.AsMemory(0, count), cancellationToken);
        }
        return output.ToArray();
    }
}
