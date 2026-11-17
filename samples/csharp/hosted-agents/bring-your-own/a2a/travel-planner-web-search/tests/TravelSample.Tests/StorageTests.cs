// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Core.Storage;
using NUnit.Framework;
using TravelAgents;

namespace TravelSample.Tests;

[NonParallelizable]
public class StorageTests
{
    private string? _previousRoot;
    private string? _previousHosting;
    private string _root = null!;
    private TripStore _store = null!;
    private FoundryStateStore _backend = null!;
    public static TripRequirements Requirements => new("SEA", "LHR", "2027-03-15", "2027-03-19", 1,
        "2027-03-16T09:00:00+00:00", "King's Cross", 2, 3500, true);

    [SetUp]
    public async Task SetUp()
    {
        _root = Path.Combine(Path.GetTempPath(), "travel-dotnet-tests-" + Guid.NewGuid().ToString("N"));
        _previousRoot = Environment.GetEnvironmentVariable("AGENTSERVER_STATE_ROOT");
        _previousHosting = Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT");
        Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", _root);
        Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", null);
        _backend = await FoundryStateStore.GetOrCreateAsync("travel-tests", itemTtlSeconds: 30 * 24 * 60 * 60);
        _store = new(_backend, "user-a", null);
    }

    [TearDown]
    public void TearDown()
    {
        Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", _previousRoot);
        Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", _previousHosting);
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }

    [Test]
    public async Task PlansAreVersionedAndIsolated()
    {
        var plan = await _store.CreateAsync(Requirements, default);
        Assert.That(plan.Version, Is.EqualTo(1));
        Assert.That(plan.Status, Is.EqualTo("needs-research"));
        var other = new TripStore(_backend, "user-b", null);
        Assert.ThrowsAsync<KeyNotFoundException>(async () => await other.GetAsync(plan.PlanId, default));
        var saved = await _store.SaveAsync(plan.PlanId, 1, "Unverified https://airline.example/",
            [new("Flight Agent", "flight-task", "https://airline.example/"), new("Hotel Agent", "hotel-task", "https://hotel.example/")], default);
        Assert.That(saved.Status, Is.EqualTo("unverified"));
        Assert.That(saved.History.Single().Specialists[0].TaskId, Is.EqualTo("flight-task"));
        Assert.That((await _store.GetAsync(plan.PlanId, default)).Version, Is.EqualTo(2));
    }

    [Test]
    public async Task LateResearchCannotOverwriteRevisedRequirements()
    {
        var plan = await _store.CreateAsync(Requirements, default);
        var revised = await _store.UpdateAsync(plan.PlanId, 1, Requirements with { BudgetUsd = 4000 }, null, default);
        Assert.That(revised.RequirementsRevision, Is.EqualTo(2));
        Assert.ThrowsAsync<InvalidOperationException>(async () => await _store.SaveAsync(plan.PlanId, 1,
            "Unverified https://airline.example/", [new("flight", "f", "https://airline.example/"), new("hotel", "h", "https://hotel.example/")], default));
        var current = await _store.GetAsync(plan.PlanId, default);
        Assert.That(current.Status, Is.EqualTo("needs-research"));
        Assert.That(current.History, Is.Empty);
    }

    [Test]
    public async Task ConcurrentEditsAllowOnlyOneVersionedWrite()
    {
        var plan = await _store.CreateAsync(Requirements, default);
        async Task<bool> Edit(decimal budget)
        {
            try
            {
                await _store.UpdateAsync(plan.PlanId, 1, Requirements with { BudgetUsd = budget }, null, default);
                return true;
            }
            catch (InvalidOperationException) { return false; }
            catch (FoundryStoragePreconditionException) { return false; }
        }
        var outcomes = await Task.WhenAll(Edit(4000), Edit(4500));
        Assert.That(outcomes.Count(success => success), Is.EqualTo(1));
        Assert.That((await _store.GetAsync(plan.PlanId, default)).Version, Is.EqualTo(2));
    }

    [Test]
    public async Task MetadataOnlyUpdateDoesNotInvalidateResearch()
    {
        var plan = await _store.CreateAsync(Requirements, default);
        var saved = await _store.SaveAsync(plan.PlanId, 1, "Unverified https://airline.example/",
            [new("flight", "f", "https://airline.example/"), new("hotel", "h", "https://hotel.example/")], default);
        var updated = await _store.UpdateAsync(plan.PlanId, saved.Version, Requirements, new() { ["label"] = "review" }, default);
        Assert.That(updated.RequirementsRevision, Is.EqualTo(1));
        Assert.That(updated.Status, Is.EqualTo("unverified"));
        Assert.That(updated.History, Has.Count.EqualTo(1));
    }

    [Test]
    public void InvalidRequirementsFailExplicitly()
    {
        Assert.Throws<ArgumentException>(() => (Requirements with { Travelers = 0 }).Validate());
        Assert.Throws<ArgumentException>(() => (Requirements with { ReturnDate = Requirements.DepartureDate }).Validate());
        Assert.Throws<ArgumentException>(() => (Requirements with { OfficeLandmark = "" }).Validate());
        Assert.Throws<ArgumentException>(() => (Requirements with { ArrivalDeadline = "2027-03-16T09:00:00" }).Validate());
    }
}
