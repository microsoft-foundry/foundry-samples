// Copyright (c) Microsoft. All rights reserved.

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace CopilotSample;

public sealed record TodoItem(string Id, string Title, bool Done);

public sealed class TaskStore
{
    private readonly string _root;
    private readonly object _gate = new();

    public TaskStore() : this(Path.Combine(
        Environment.GetEnvironmentVariable("HOME")
            ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        ".github-copilot-activity"))
    {
    }

    public TaskStore(string root)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(root);
        _root = Path.GetFullPath(root);
    }

    public static string SessionId(string conversationId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);
        return "conv-" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(conversationId)))[..32];
    }

    public string Workspace(string conversationId)
    {
        var path = Path.Combine(_root, SessionId(conversationId));
        Directory.CreateDirectory(path);
        return path;
    }

    public IReadOnlyList<TodoItem> List(string conversationId)
    {
        lock (_gate)
        {
            return Load(conversationId);
        }
    }

    public TodoItem Add(string conversationId, string title)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(title);
        title = title.Trim();
        lock (_gate)
        {
            var tasks = Load(conversationId);
            var existing = tasks.Find(task => !task.Done && task.Title.Equals(title, StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
            {
                return existing;
            }

            var task = new TodoItem(Guid.NewGuid().ToString("N")[..8], title, false);
            tasks.Add(task);
            Save(conversationId, tasks);
            return task;
        }
    }

    public void Complete(string conversationId, string taskId)
    {
        lock (_gate)
        {
            var tasks = Load(conversationId);
            var index = tasks.FindIndex(task => task.Id == taskId);
            if (index < 0)
            {
                throw new ArgumentException("Task not found.", nameof(taskId));
            }

            tasks[index] = tasks[index] with { Done = true };
            Save(conversationId, tasks);
        }
    }

    public void Delete(string conversationId, string taskId)
    {
        lock (_gate)
        {
            var tasks = Load(conversationId);
            if (tasks.RemoveAll(task => task.Id == taskId) == 0)
            {
                throw new ArgumentException("Task not found.", nameof(taskId));
            }

            Save(conversationId, tasks);
        }
    }

    private List<TodoItem> Load(string conversationId)
    {
        var path = Path.Combine(Workspace(conversationId), "tasks.json");
        return File.Exists(path)
            ? JsonSerializer.Deserialize<List<TodoItem>>(File.ReadAllText(path))
                ?? throw new InvalidDataException("The task store is invalid.")
            : [];
    }

    private void Save(string conversationId, List<TodoItem> tasks)
    {
        var path = Path.Combine(Workspace(conversationId), "tasks.json");
        var temporaryPath = path + ".tmp";
        File.WriteAllText(temporaryPath, JsonSerializer.Serialize(tasks));
        File.Move(temporaryPath, path, overwrite: true);
    }
}
