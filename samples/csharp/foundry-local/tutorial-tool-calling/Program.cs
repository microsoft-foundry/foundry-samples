// <complete_code>
// <imports>
using System.Text.Json;
using Microsoft.AI.Foundry.Local;
using Microsoft.Extensions.Logging;
// </imports>

CancellationToken ct = CancellationToken.None;

// <tool_definitions>
// --- Tool definitions and implementations ---
var toolDefinitions = new[]
{
    new
    {
        Name = "get_weather",
        Description = "Get the current weather for a location",
        Schema =
            """
            {
              "type": "object",
              "properties": {
                "location": { "type": "string", "description": "The city or location" },
                "unit": {
                  "type": "string",
                  "description": "Temperature unit",
                  "enum": ["celsius", "fahrenheit"]
                }
              },
              "required": ["location"]
            }
            """
    },
    new
    {
        Name = "calculate",
        Description = "Perform a math calculation",
        Schema =
            """
            {
              "type": "object",
              "properties": {
                "expression": { "type": "string", "description": "The math expression to evaluate" }
              },
              "required": ["expression"]
            }
            """
    }
};

string ExecuteTool(string functionName, JsonElement arguments)
{
    switch (functionName)
    {
        case "get_weather":
            var location = arguments.GetProperty("location").GetString() ?? "unknown";
            var unit = arguments.TryGetProperty("unit", out var u)
                ? u.GetString() ?? "celsius"
                : "celsius";
            var temp = unit == "celsius" ? 22 : 72;
            return JsonSerializer.Serialize(new
            {
                location,
                temperature = temp,
                unit,
                condition = "Sunny"
            });

        case "calculate":
            var expression = arguments.GetProperty("expression").GetString() ?? "";
            try
            {
                var result = new System.Data.DataTable().Compute(expression, null);
                return JsonSerializer.Serialize(new { expression, result = result?.ToString() });
            }
            catch (Exception ex)
            {
                return JsonSerializer.Serialize(new { error = ex.Message });
            }

        default:
            return JsonSerializer.Serialize(new { error = $"Unknown function: {functionName}" });
    }
}
// </tool_definitions>

// <init>
// --- Main application ---
var config = new Configuration
{
    AppName = "foundry_local_samples",
    LogLevel = Microsoft.AI.Foundry.Local.LogLevel.Information
};

using var loggerFactory = LoggerFactory.Create(builder =>
{
    builder.SetMinimumLevel(Microsoft.Extensions.Logging.LogLevel.Information);
});
var logger = loggerFactory.CreateLogger<Program>();

await FoundryLocalManager.CreateAsync(config, logger);
var mgr = FoundryLocalManager.Instance;

var currentEp = "";
await mgr.DownloadAndRegisterEpsAsync((epName, percent) =>
{
    if (epName != currentEp)
    {
        if (currentEp != "") Console.WriteLine();
        currentEp = epName;
    }
    Console.Write($"\r  {epName.PadRight(30)}  {percent,6:F1}%");
});
if (currentEp != "") Console.WriteLine();

var catalog = await mgr.GetCatalogAsync();
var model = await catalog.GetModelAsync("qwen2.5-0.5b")
    ?? throw new Exception("Model not found");

await model.DownloadAsync(progress =>
{
    Console.Write($"\rDownloading model: {progress:F2}%");
    if (progress >= 100f) Console.WriteLine();
});

await model.LoadAsync();
Console.WriteLine("Model loaded and ready.");

using var chatSession = new ChatSession(model);
chatSession.SetOptions(new RequestOptions { ToolChoice = ToolChoice.Auto });
foreach (var tool in toolDefinitions)
{
    chatSession.AddToolDefinition(tool.Name, tool.Description, tool.Schema);
}
// </init>

// <tool_loop>
Console.WriteLine("\nTool-calling assistant ready! Type 'quit' to exit.\n");

while (true)
{
    Console.Write("You: ");
    var userInput = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(userInput) ||
        userInput.Equals("quit", StringComparison.OrdinalIgnoreCase) ||
        userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    using var request = new Request();
    if (chatSession.TurnCount == 0)
    {
        request.AddItem(MessageItem.System(
            "You are a helpful assistant with access to tools. Use them when needed."));
    }
    request.AddItem(MessageItem.User(userInput));

    using var response = await chatSession.ProcessRequestAsync(request, ct);
    var toolCalls = response.OfType<ToolCallItem>()
        .Select(call => (call.CallId, call.Name, call.Arguments))
        .ToList();

    if (toolCalls.Count > 0)
    {
        using var toolRequest = new Request();
        foreach (var toolCall in toolCalls)
        {
            using var argumentsDocument = JsonDocument.Parse(toolCall.Arguments);
            var arguments = argumentsDocument.RootElement;
            Console.WriteLine($"  Tool call: {toolCall.Name}({arguments})");
            var result = ExecuteTool(toolCall.Name, arguments);
            toolRequest.AddItem(new ToolResultItem(toolCall.CallId, result));
        }

        using var finalResponse = await chatSession.ProcessRequestAsync(toolRequest, ct);
        var answer = GetResponseText(finalResponse);
        Console.WriteLine($"Assistant: {answer}\n");
    }
    else
    {
        Console.WriteLine($"Assistant: {GetResponseText(response)}\n");
    }
}

chatSession.Dispose();
await model.UnloadAsync();
Console.WriteLine("Model unloaded. Goodbye!");
// </tool_loop>
// </complete_code>

static string GetResponseText(Response response) =>
    string.Concat(
        response.OfType<MessageItem>()
            .SelectMany(message => message.Parts)
            .OfType<TextItem>()
            .Where(text => text.Type == TextItemType.Default)
            .Select(text => text.Text));
