// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Nodes;
using Microsoft.Agents.Core.Models;

namespace CopilotSample;

public static class TaskCards
{
    public const string ContentType = "application/vnd.microsoft.card.adaptive";

    public static JsonObject Build(IReadOnlyList<TodoItem> tasks)
    {
        var body = new JsonArray
        {
            new JsonObject { ["type"] = "TextBlock", ["text"] = "Your to-dos", ["weight"] = "Bolder", ["size"] = "Medium" }
        };
        foreach (var task in tasks)
        {
            var actions = new JsonArray();
            if (!task.Done)
            {
                actions.Add(Action("Done", "complete_task", task.Id));
            }
            actions.Add(Action("Delete", "delete_task", task.Id));
            body.Add(new JsonObject
            {
                ["type"] = "Container",
                ["separator"] = true,
                ["items"] = new JsonArray
                {
                    new JsonObject { ["type"] = "TextBlock", ["text"] = task.Done ? $"~~{task.Title}~~" : task.Title, ["wrap"] = true },
                    new JsonObject { ["type"] = "ActionSet", ["actions"] = actions }
                }
            });
        }

        if (tasks.Count == 0)
        {
            body.Add(new JsonObject { ["type"] = "TextBlock", ["text"] = "No tasks yet. Add one below." });
        }
        body.Add(new JsonObject { ["type"] = "Input.Text", ["id"] = "newTask", ["placeholder"] = "Add a new task" });
        return new JsonObject
        {
            ["$schema"] = "http://adaptivecards.io/schemas/adaptive-card.json",
            ["type"] = "AdaptiveCard",
            ["version"] = "1.5",
            ["body"] = body,
            ["actions"] = new JsonArray { Action("Add", "add_task"), Action("Refresh", "refresh_tasks") }
        };
    }

    public static Attachment Attachment(IReadOnlyList<TodoItem> tasks) =>
        new() { ContentType = ContentType, Content = Build(tasks) };

    private static JsonObject Action(string title, string verb, string? taskId = null) =>
        new()
        {
            ["type"] = "Action.Execute",
            ["title"] = title,
            ["verb"] = verb,
            ["data"] = new JsonObject { ["taskId"] = taskId }
        };
}
