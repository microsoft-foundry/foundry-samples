// Copyright (c) Microsoft. All rights reserved.

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Azure.AI.AgentServer.Core.Storage;

namespace TravelAgents;

public sealed record TripRequirements(
    string Origin, string Destination, string DepartureDate, string ReturnDate,
    int Travelers, string ArrivalDeadline, string OfficeLandmark, decimal MaxOfficeDistanceKm,
    decimal BudgetUsd, bool Refundable)
{
    public void Validate()
    {
        if (new[] { Origin, Destination, OfficeLandmark }.Any(value => string.IsNullOrWhiteSpace(value) || value.Length > 200))
            throw new ArgumentException("Supply origin, destination and a public office landmark (not a private address).");
        if (!DateOnly.TryParseExact(DepartureDate, "yyyy-MM-dd", out var start) ||
            !DateOnly.TryParseExact(ReturnDate, "yyyy-MM-dd", out var end) || end <= start ||
            !Regex.IsMatch(ArrivalDeadline, @"(?:Z|[+-]\d{2}:\d{2})$") ||
            !DateTimeOffset.TryParse(ArrivalDeadline, out var arrival) || arrival.Date < start.ToDateTime(TimeOnly.MinValue) ||
            arrival.Date > end.ToDateTime(TimeOnly.MinValue))
            throw new ArgumentException("Use YYYY-MM-DD travel dates and an arrival deadline with date, time and UTC offset within the trip.");
        if (Travelers is < 1 or > 20 || BudgetUsd <= 0 || MaxOfficeDistanceKm <= 0)
            throw new ArgumentException("Travelers must be 1-20; budget and office distance must be positive.");
    }
}

public sealed record Recommendation(int RequirementsRevision, string Answer, IReadOnlyList<SpecialistAnswer> Specialists, DateTimeOffset SavedAt);
public sealed record TripPlan(string PlanId, int Version, int RequirementsRevision, TripRequirements Requirements,
    string Status, Dictionary<string, string> Metadata, IReadOnlyList<Recommendation> History);

public sealed class TripStore(FoundryStateStore store, string owner, string? callId)
{
    public static string Key(string owner, string planId)
    {
        if (!Guid.TryParseExact(planId, "N", out _)) throw new ArgumentException("Plan ID must be a 32-character GUID.", nameof(planId));
        string partition = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(owner))).ToLowerInvariant();
        return $"trip:{partition}:{planId}";
    }

    public async Task<TripPlan> CreateAsync(TripRequirements requirements, CancellationToken ct)
    {
        requirements.Validate();
        var plan = new TripPlan(Guid.NewGuid().ToString("N"), 1, 1, requirements, "needs-research", [], []);
        await store.CreateItemAsync(Key(owner, plan.PlanId), Value(plan), Tags, callId, ct);
        return plan;
    }

    public async Task<TripPlan> GetAsync(string id, CancellationToken ct) =>
        Decode(await store.GetItemAsync(Key(owner, id), callId, ct) ?? throw new KeyNotFoundException("Plan not found in this user's partition."));

    public async Task<TripPlan> UpdateAsync(string id, int expectedVersion, TripRequirements requirements,
        Dictionary<string, string>? metadata, CancellationToken ct)
    {
        requirements.Validate();
        var item = await ReadAsync(id, ct);
        var current = Decode(item);
        RequireVersion(current, expectedVersion);
        bool changed = current.Requirements != requirements;
        var next = current with
        {
            Version = current.Version + 1,
            Requirements = requirements,
            RequirementsRevision = current.RequirementsRevision + (changed ? 1 : 0),
            Status = changed ? "needs-research" : current.Status,
            Metadata = metadata ?? current.Metadata
        };
        await store.SetItemAsync(Key(owner, id), Value(next), Tags, item.Etag, false, callId, ct);
        return next;
    }

    public async Task<TripPlan> SaveAsync(string id, int expectedVersion, string answer,
        IReadOnlyList<SpecialistAnswer> specialists, CancellationToken ct)
    {
        if (specialists.Count != 2 || specialists.Any(s => string.IsNullOrEmpty(s.TaskId)) ||
            string.IsNullOrWhiteSpace(answer) || ResearchRuntime.SourceUrls(answer).Length == 0)
            throw new ArgumentException("Save requires cited research and two verified specialist Task IDs.");
        if (ResearchRuntime.SourceUrls(answer).Any(url =>
            !specialists.Any(specialist => ResearchRuntime.SourceUrls(specialist.Answer).Contains(url))))
            throw new ArgumentException("Saved citations must occur in the verified specialist answers.");
        var item = await ReadAsync(id, ct);
        var current = Decode(item);
        RequireVersion(current, expectedVersion);
        var next = current with
        {
            Version = current.Version + 1,
            Status = "unverified",
            History = current.History.Append(new Recommendation(current.RequirementsRevision, answer, specialists, DateTimeOffset.UtcNow)).ToArray()
        };
        await store.SetItemAsync(Key(owner, id), Value(next), Tags, item.Etag, false, callId, ct);
        return next;
    }

    private async Task<StateStoreItem> ReadAsync(string id, CancellationToken ct) =>
        await store.GetItemAsync(Key(owner, id), callId, ct) ??
            throw new KeyNotFoundException("Plan not found in this user's partition.");
    private static readonly Dictionary<string, string> Tags = new() { ["sample"] = "a2a-travel" };
    private static TripPlan Decode(StateStoreItem? item) =>
        item?.Value.TryGetValue("plan", out var data) == true
            ? data.ToObjectFromJson<TripPlan>() ?? throw new InvalidDataException("Plan snapshot is null.")
            : throw new InvalidDataException("Plan snapshot is missing or corrupt.");

    private static Dictionary<string, BinaryData> Value(TripPlan plan)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(plan);
        if (bytes.Length > 64 * 1024) throw new ArgumentException("Plan history and metadata exceed the 64 KiB sample limit.");
        return new() { ["plan"] = BinaryData.FromBytes(bytes) };
    }

    public static void RequireVersion(TripPlan plan, int expected)
    {
        if (plan.Version != expected)
            throw new InvalidOperationException($"Plan version conflict: expected {expected}, current {plan.Version}. Read the current plan before retrying.");
    }
}
