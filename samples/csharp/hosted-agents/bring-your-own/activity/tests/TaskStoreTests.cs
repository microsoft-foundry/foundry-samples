// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using CopilotSample;
using NUnit.Framework;

namespace ActivitySamples.Tests;

[TestFixture]
public sealed class TaskStoreTests
{
    private string _root = null!;
    private TaskStore _store = null!;

    [SetUp]
    public void SetUp()
    {
        _root = Path.Combine(Path.GetTempPath(), "activity-samples-tests", Guid.NewGuid().ToString("N"));
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

    [Test]
    public void TasksPersistAcrossInstancesAndRemainConversationScoped()
    {
        var task = _store.Add("one", "Buy milk");
        _store.Complete("one", task.Id);
        var reloaded = new TaskStore(_root);
        Assert.That(reloaded.List("one"), Is.EqualTo(new[] { task with { Done = true } }));
        Assert.That(reloaded.List("two"), Is.Empty);
        reloaded.Delete("one", task.Id);
        Assert.That(_store.List("one"), Is.Empty);
    }

    [Test]
    public void DuplicateOpenTasksAreIdempotent()
    {
        var task = _store.Add("one", "Buy milk");
        Assert.That(_store.Add("one", " BUY MILK "), Is.EqualTo(task));
        Assert.That(_store.List("one"), Has.Count.EqualTo(1));
    }

    [Test]
    public void CompletedTaskCanBeAddedAgain()
    {
        var task = _store.Add("one", "Buy milk");
        _store.Complete("one", task.Id);
        Assert.That(_store.Add("one", "Buy milk").Id, Is.Not.EqualTo(task.Id));
    }

    [Test]
    public void ConcurrentWritesDoNotLoseTasks()
    {
        Parallel.For(0, 25, index => _store.Add("one", $"Task {index}"));
        Assert.That(_store.List("one"), Has.Count.EqualTo(25));
    }

    [TestCase("")]
    [TestCase("   ")]
    public void EmptyTitlesAreRejected(string title) =>
        Assert.Throws<ArgumentException>(() => _store.Add("one", title));

    [Test]
    public void UnknownTaskIsReported()
    {
        Assert.Throws<ArgumentException>(() => _store.Complete("one", "missing"));
        Assert.Throws<ArgumentException>(() => _store.Delete("one", "missing"));
    }

    [Test]
    public void CorruptTaskStoreIsNotSilentlyReset()
    {
        File.WriteAllText(Path.Combine(_store.Workspace("one"), "tasks.json"), "not json");
        Assert.Throws<JsonException>(() => _store.List("one"));
    }

    [Test]
    public void SessionIdsAreStableCompactAndPathSafe()
    {
        var conversation = "../../" + new string('a', 200);
        var id = TaskStore.SessionId(conversation);
        Assert.That(id, Has.Length.EqualTo(37));
        Assert.That(id, Does.Match("^conv-[a-f0-9]{32}$"));
        Assert.That(TaskStore.SessionId(conversation), Is.EqualTo(id));
        Assert.That(TaskStore.SessionId("a/b"), Is.Not.EqualTo(TaskStore.SessionId("a_b")));
    }

    [Test]
    public void CardContainsActionsAndNoAutomaticRefreshLoop()
    {
        var task = _store.Add("one", "Buy milk");
        var card = TaskCards.Build(_store.List("one"));
        Assert.That(card["version"]!.GetValue<string>(), Is.EqualTo("1.5"));
        Assert.That(card.ToJsonString(), Does.Contain("complete_task").And.Contain("delete_task").And.Contain("newTask"));
        Assert.That(card.ContainsKey("refresh"), Is.False);
        _store.Complete("one", task.Id);
        Assert.That(TaskCards.Build(_store.List("one")).ToJsonString(), Does.Not.Contain("complete_task"));
    }
}
