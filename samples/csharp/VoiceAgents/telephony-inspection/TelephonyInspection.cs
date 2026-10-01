// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

// This sample demonstrates how to inspect a voice agent's telephony configuration and call
// history. It is read-only: it does not place, transfer, end, or record calls.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;

// Set these values in .env for an existing voice agent with telephony configured.
string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.");
string agentName = Environment.GetEnvironmentVariable("FOUNDRY_VOICE_AGENT_NAME")
    ?? throw new InvalidOperationException("Set FOUNDRY_VOICE_AGENT_NAME before running this sample.");

AIProjectClient projectClient = new(new Uri(projectEndpoint), new DefaultAzureCredential());
BetaVoiceAgentsTelephony telephonyClient = projectClient.AgentAdministrationClient.GetBetaVoiceAgentTelephony();

Console.WriteLine("Listing telephony bindings...");
await foreach (TelephonyBindingListItem binding in telephonyClient.GetTelephonyBindingsAsync(agentName))
{
    TelephonyBinding details = await telephonyClient.GetTelephonyBindingAsync(agentName, binding.Id);
    // Avoid logging phone numbers, webhook URLs, or caller information.
    Console.WriteLine($"Binding type: {details.GetType().Name}, status: {details.Status}");
}

Console.WriteLine("\nReading configured transfer targets...");
TelephonyTransferTargets targets = await telephonyClient.GetTelephonyTransferTargetsAsync(agentName);
Console.WriteLine($"Transfer target names: {string.Join(", ", targets.TransferTargets.Select(target => target.Name))}");

Console.WriteLine("\nReading the most recent page of call history...");
int callCount = 0;
await foreach (TelephonyCallSummary call in telephonyClient.GetTelephonyCallsAsync(agentName, order: AgentListOrder.Descending, limit: 5))
{
    callCount++;

    try
    {
        TelephonyCallRecord details = await telephonyClient.GetTelephonyCallAsync(agentName, call.Id);
        Console.WriteLine($"Call status: {details.Status}, phase: {details.Phase}");
        Console.WriteLine($"Lifecycle events: {details.Events.Count}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Call {call.Id}: unable to read full details ({ex.Message})");
    }
}
if (callCount == 0)
{
    Console.WriteLine("No calls found for this agent.");
}
