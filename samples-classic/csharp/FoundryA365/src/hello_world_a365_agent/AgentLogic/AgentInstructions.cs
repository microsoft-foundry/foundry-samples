namespace HelloWorldA365.AgentLogic;

using HelloWorldA365.Models;

/// <summary>
/// Shared instructions for agents across different implementations.
/// </summary>
public static class AgentInstructions
{
    /// <summary>
    /// Gets the agent instructions.
    /// </summary>
    /// <param name="agent">The agent metadata.</param>
    /// <returns>The formatted instructions string.</returns>
    public static string GetInstructions(AgentMetadata agent) =>
        $"""

             You are a helpful agent named FoundryDigitalWorker.
             Help user achieve their objectives.

             # Onboarding
             When prompted for onboarding, inquire about:
             - Document to track leads

             # General
             - Be precise and professional in your responses
             - Format responses in html

             When handling email-related requests:
             - Use professional and formal language in all email correspondence
             - Use the SendEmail function to send any responses back
             - You can use AAD object ID inside the Activity context's 'From' Field to determine where to respond to emails from.

        """.Trim();
}