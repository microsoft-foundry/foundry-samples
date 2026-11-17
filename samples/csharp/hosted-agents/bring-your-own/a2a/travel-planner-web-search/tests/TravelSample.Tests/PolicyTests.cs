// Copyright (c) Microsoft. All rights reserved.

using NUnit.Framework;
using TravelAgents;

namespace TravelSample.Tests;

public class PolicyTests
{
    private const string Project = "https://test.services.ai.azure.com/api/projects/project";

    [TestCase("https://evil.example/agents/x")]
    [TestCase("https://test.services.ai.azure.com/api/projects/project-two/agents/x")]
    [TestCase("https://user:password@test.services.ai.azure.com/api/projects/project/agents/x")]
    [TestCase("https://test.services.ai.azure.com/api/projects/project/agents/../x")]
    [TestCase("https://test.services.ai.azure.com/api/projects/project/agents/%2e%2e/x")]
    [TestCase("http://localhost:8088/a2a")]
    public void HostedAgentUrlRejectsUntrustedTargets(string url) =>
        Assert.Throws<ArgumentException>(() => Settings.ValidateAgentUrl(url, Project, true));

    [Test]
    public void LocalAgentUrlAllowsOnlyLoopback()
    {
        Assert.DoesNotThrow(() => Settings.ValidateAgentUrl("http://127.0.0.1:8088/a2a", Project, false));
        Assert.Throws<ArgumentException>(() => Settings.ValidateAgentUrl("http://192.0.2.1/a2a", Project, false));
    }

    [TestCase("https://evil.example/mcp?api-version=v1")]
    [TestCase("https://test.services.ai.azure.com/api/projects/project/agents/x/mcp?api-version=v1")]
    [TestCase("https://test.services.ai.azure.com/api/projects/project/toolboxes/x/mcp")]
    public void ToolboxUrlIsProjectScoped(string url) =>
        Assert.Throws<ArgumentException>(() => Settings.ValidateToolboxUrl(url, Project));

    [Test]
    public void SearchBudgetEnforcesExactlyTwoAdmissions()
    {
        var budget = new SearchBudget();
        Assert.That(budget.TryAcquire(), Is.True);
        Assert.That(budget.TryAcquire(), Is.True);
        Assert.That(budget.TryAcquire(), Is.False);
        Assert.That(budget.TryAcquire(), Is.False);
    }

    [Test]
    public void SearchRequiresSuccessfulActualCitations()
    {
        SearchReceipt[] searches = [new("failed", false, []), new("success", true, ["https://airline.example/fares"])];
        Assert.DoesNotThrow(() => ResearchRuntime.ValidateResearch("Unverified https://airline.example/fares", searches));
        Assert.Throws<ResearchException>(() => ResearchRuntime.ValidateResearch("Invented https://other.example/", searches));
        var failure = Assert.Throws<ResearchException>(() => ResearchRuntime.ValidateResearch("No sources", [searches[0]]));
        Assert.That(failure!.Searches.Single().Success, Is.False);
        Assert.Throws<ResearchException>(() => ResearchRuntime.ValidateResearch(
            "https://airline.example/fares", [searches[1], searches[1], searches[1]]));
    }

    [Test]
    public void PlanKeysPreserveUserIsolationAndOpaqueIdentity()
    {
        string id = Guid.NewGuid().ToString("N");
        Assert.That(TripStore.Key("user-a", id), Is.Not.EqualTo(TripStore.Key("user-b", id)));
        Assert.That(TripStore.Key("user-a", id).Length, Is.LessThanOrEqualTo(128));
        Assert.Throws<ArgumentException>(() => TripStore.Key("user", "../other-user"));
    }

    [Test]
    public void PlatformHeadersNeverForwardUserIdentity() =>
        Assert.That(Settings.Headers("call", null).Keys, Is.EquivalentTo(new[] { "x-agent-foundry-call-id" }));

    [Test]
    public void EachRoleAdvertisesNativeA2A10()
    {
        foreach (string role in new[] { "planner", "flights", "hotels" })
        {
            var card = TravelAgent.CreateCard(role, "http://localhost:8088/a2a");
            Assert.That(card.SupportedInterfaces.Single().ProtocolVersion, Is.EqualTo("1.0"));
            Assert.That(card.Skills.Single().Id, Is.EqualTo(role));
        }
        Assert.Throws<ArgumentException>(() => TravelAgent.CreateCard("unknown", "http://localhost:8088/a2a"));
    }
}
