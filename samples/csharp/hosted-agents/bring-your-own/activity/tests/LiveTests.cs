// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using CopilotSample;
using GitHub.Copilot;
using Microsoft.Extensions.Configuration;
using NUnit.Framework;

namespace ActivitySamples.Tests;

[TestFixture]
[Category("Live")]
public sealed class LiveTests
{
    [Test]
    public async Task CopilotUsesFoundryModelToolsConversationHistoryAndSharedFiles()
    {
        var configuration = new ConfigurationBuilder().AddEnvironmentVariables().Build();
        Assert.That(configuration["FOUNDRY_PROJECT_ENDPOINT"], Is.Not.Null.And.Not.Empty,
            "Set FOUNDRY_PROJECT_ENDPOINT before running live tests.");
        Assert.That(configuration["AZURE_AI_MODEL_DEPLOYMENT_NAME"], Is.Not.Null.And.Not.Empty,
            "Set AZURE_AI_MODEL_DEPLOYMENT_NAME before running live tests.");
        var root = Path.Combine(Path.GetTempPath(), "activity-live-tests", Guid.NewGuid().ToString("N"));
        var store = new TaskStore(root);
        var conversation = "live-" + Guid.NewGuid().ToString("N");
        try
        {
            await using var assistant = new CopilotAssistant(configuration, store);
            await assistant.StartAsync(CancellationToken.None);
            try
            {
                var (added, _) = await AskAsync("Add a task titled activity-sample-check using add_task.");
                Assert.That(added, Is.Not.Empty);
                var task = store.List(conversation).Single();
                Assert.That(task.Title, Is.EqualTo("activity-sample-check"));

                var (_, listed) = await AskAsync("Show my tasks using list_tasks.");
                Assert.That(listed.ShowTasks, Is.True);

                await AskAsync($"Mark task {task.Id} as done using complete_task.");
                Assert.That(store.List(conversation).Single().Done, Is.True);

                var source = Path.Combine(store.Workspace(conversation), "shared-test.txt");
                await File.WriteAllTextAsync(source, "The verification code is ACTIVITY-7319.");
                var (read, _) = await AskAsync("Read the attached file and tell me its verification code.",
                    [new AttachmentFile { Path = source, DisplayName = "shared-test.txt" }]);
                Assert.That(read, Does.Contain("ACTIVITY-7319"));

                var (_, generated) = await AskAsync(
                    "Create a file named activity-report.txt in your working directory containing ACTIVITY-7319, "
                    + "then call deliver_file with its absolute path.");
                Assert.That(generated.Files, Has.Count.EqualTo(1));
                Assert.That(await File.ReadAllTextAsync(generated.Files.Single()), Does.Contain("ACTIVITY-7319"));
                TestContext.Progress.WriteLine("LIVE: Foundry model, add/list/complete tools, resumed conversation, file reading and generation passed.");
            }
            finally
            {
                await assistant.StopAsync(CancellationToken.None);
            }

            async Task<(string Text, AssistantResult Result)> AskAsync(string prompt, IList<Attachment>? attachments = null)
            {
                var text = new StringBuilder();
                var result = await assistant.ReplyAsync(conversation, prompt, attachments ?? [],
                    chunk => text.Append(chunk), _ => { }, CancellationToken.None);
                return (text.ToString(), result);
            }
        }
        finally
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }
}
