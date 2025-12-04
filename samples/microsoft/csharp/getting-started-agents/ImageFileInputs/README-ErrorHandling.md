# How to Get Error Details for Failed Agent Runs

## The Problem
When an Azure AI Agents run fails, you may see the status as "Failed" but not know the specific reason why it failed.

## The Solution
After polling for run completion, check the run status and access the error details:

```csharp
// After your polling loop completes
if (run.Status != RunStatus.Completed)
{
    // Get comprehensive error information
    Console.WriteLine($"Run failed with status: {run.Status}");
    Console.WriteLine($"Failed at: {run.FailedAt}");
    Console.WriteLine($"Error message: {run.LastError?.Message}");  // This is the key!
    Console.WriteLine($"Error code: {run.LastError?.Code}");
    
    // Throw exception or return error as appropriate
    throw new Exception($"Run failed: {run.LastError?.Message}");
}
```

## Available Error Properties

| Property | Description |
|----------|-------------|
| `run.Status` | The final status (Failed, Cancelled, Expired, etc.) |
| `run.FailedAt` | Timestamp when the run failed |
| `run.LastError?.Message` | **Detailed error message explaining why it failed** |
| `run.LastError?.Code` | Error code for programmatic handling |

## Key Points
- **Always check `run.Status != RunStatus.Completed`** after polling
- **`run.LastError?.Message`** contains the actual reason for failure
- Don't just log the status - get the detailed error message
- The error information helps debug issues like invalid models, quota limits, file format problems, etc.

## Example Output
Instead of just getting:
```
Run status: Failed - 2024-01-15T10:30:00Z
```

You'll get detailed information like:
```
Run failed with status: Failed
Failed at: 2024-01-15T10:30:00Z
Error message: The model '03-mini' is not available in this region. Please use 'gpt-4' instead.
Error code: InvalidModel
```

See `ErrorHandlingExample.cs` for a complete implementation example.