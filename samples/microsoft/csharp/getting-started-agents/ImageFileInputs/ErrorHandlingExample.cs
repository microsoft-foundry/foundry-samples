// Example showing comprehensive error handling for failed runs
// This addresses the common issue where users can see a run has failed
// but cannot determine the specific reason for the failure.

using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using System.Text;

// Your existing code...
// ... (client setup, agent creation, thread creation, message creation)

ThreadRun run = await client.Runs.CreateRunAsync(
    threadId: thread.Id,
    assistantId: agent.Id
);

StringBuilder output = new StringBuilder();

// Poll for completion
do
{
    await Task.Delay(TimeSpan.FromMilliseconds(500));
    run = await client.Runs.GetRunAsync(thread.Id, run.Id);
}
while (run.Status == RunStatus.Queued
    || run.Status == RunStatus.InProgress
    || run.Status == RunStatus.RequiresAction);

// CHECK FOR ERRORS - This is what was missing in the original user code
if (run.Status != RunStatus.Completed)
{
    // Log comprehensive error information for debugging
    output.AppendLine($"❌ Run failed!");
    output.AppendLine($"Status: {run.Status}");
    output.AppendLine($"Failed at: {run.FailedAt}");
    output.AppendLine($"Error message: {run.LastError?.Message}");
    output.AppendLine($"Error code: {run.LastError?.Code}");
    
    // Option 1: Throw exception with detailed error information
    throw new Exception($"Run did not complete successfully. Status: {run.Status}, " +
                       $"Failed at: {run.FailedAt}, Error: {run.LastError?.Message}");
    
    // Option 2: Return error information instead of throwing (for APIs)
    // return new BadRequestObjectResult(output.ToString());
}
else
{
    output.AppendLine($"✅ Run completed successfully!");
}

// Continue with processing messages only if run completed successfully
AsyncPageable<PersistentThreadMessage> messages = client.Messages.GetMessagesAsync(
    threadId: thread.Id,
    order: ListSortOrder.Descending);

await foreach (PersistentThreadMessage threadMessage in messages)
{
    foreach (MessageContent content in threadMessage.ContentItems)
    {
        switch (content)
        {
            case MessageTextContent textItem:
                Console.WriteLine($"[{threadMessage.Role}]: {textItem.Text}");
                output.AppendLine($"[{threadMessage.Role}]: {textItem.Text}");
                break;

            case MessageImageFileContent fileItem:
                Console.WriteLine($"[{threadMessage.Role}]: Image File (internal ID): {fileItem.FileId}");
                output.AppendLine($"[{threadMessage.Role}]: Image File (internal ID): {fileItem.FileId}");
                break;
        }
    }
}

// Cleanup
await client.Files.DeleteFileAsync(uploadedFile.Id);
await client.Threads.DeleteThreadAsync(threadId: thread.Id);
await client.Administration.DeleteAgentAsync(agentId: agent.Id);

return new OkObjectResult(output.ToString());