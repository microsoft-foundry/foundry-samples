namespace HelloWorldA365.Mcp;

using System.Text.Json;
using Microsoft.SemanticKernel;

/// <summary>
/// Wrapper class for MCP functions that allows parameter inspection and logging
/// </summary>
public class McpFunctionWrapper(
    KernelFunction originalFunction,
    string functionName,
    ILogger logger,
    IConfiguration configuration)
{
    public KernelFunction CreateWrappedFunction()
    {
        return KernelFunctionFactory.CreateFromMethod(
            method: InvokeWithLogging,
            functionName: functionName,
            description: originalFunction.Description,
            parameters: originalFunction.Metadata.Parameters,
            returnParameter: originalFunction.Metadata.ReturnParameter
        );
    }

    private async Task<object?> InvokeWithLogging(KernelArguments arguments, Kernel kernel, CancellationToken cancellationToken = default)
    {
        if (configuration["ToolMCPServer:EnableMCPFunctionLogging"]?.ToLower() != "true")
        {
            // If logging is disabled, just invoke the original function directly
            var result = await originalFunction.InvokeAsync(kernel, arguments, cancellationToken);
            return result.GetValue<object>();
        }

        try
        {
            // Log function invocation with parameters
            logger.LogInformation("Invoking MCP function: {FunctionName}", functionName);
            var processedArguments = ProcessParameters(arguments);
            if (processedArguments.Count > 0)
            {
                var parametersJson = JsonSerializer.Serialize(
                    arguments.ToDictionary(kvp => kvp.Key, kvp => kvp.Value),
                    new JsonSerializerOptions { WriteIndented = true }
                );
                logger.LogInformation("MCP Function Parameters for {FunctionName}:\n{Parameters}", functionName, parametersJson);
            }
            else
            {
                logger.LogInformation("MCP Function {FunctionName} called with no parameters", functionName);
            }

            // Invoke the original function with processed arguments
            var result = await originalFunction.InvokeAsync(kernel, processedArguments, cancellationToken);

            // Log the result
            var resultValue = result.GetValue<object>()?.ToString() ?? "null";
            logger.LogInformation("MCP Function {FunctionName} result: {Result}", functionName, resultValue);

            return result.GetValue<object>();
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Error executing MCP function {FunctionName}", functionName);
            throw;
        }
    }

    /// <summary>
    /// Processes parameters to handle specific parameter name transformations
    /// </summary>
    /// <param name="arguments">Original arguments</param>
    /// <returns>Processed arguments with transformations applied</returns>
    private KernelArguments ProcessParameters(KernelArguments arguments)
    {
        var processedArguments = new KernelArguments();

        foreach (var kvp in arguments)
        {
            var parameterName = kvp.Key;
            var parameterValue = kvp.Value;

            try
            {
                // Handle "message" or "body" parameters - parse from string to JSON object if they are strings
                if ((parameterName.Equals("message", StringComparison.OrdinalIgnoreCase) ||
                     parameterName.Equals("body", StringComparison.OrdinalIgnoreCase)) &&
                    parameterValue is string stringValue && !string.IsNullOrWhiteSpace(stringValue))
                {
                    try
                    {
                        // Try to parse as JSON - if it's already a JSON string, parse it to object
                        var jsonObject = JsonSerializer.Deserialize<object>(stringValue);
                        processedArguments[parameterName] = jsonObject;
                        logger.LogInformation("Parsed parameter '{ParameterName}' from string to JSON object for function {FunctionName}", parameterName, functionName);
                    }
                    catch (JsonException)
                    {
                        // If it's not valid JSON, treat it as plain text and wrap it in a simple object
                        var textObject = new { content = stringValue };
                        processedArguments[parameterName] = textObject;
                        logger.LogInformation("Wrapped parameter '{ParameterName}' plain text in object for function {FunctionName}", parameterName, functionName);
                    }
                }
                // Handle "saveToSentItem" parameter - convert from string to boolean
                else if (parameterName.Equals("saveToSentItem", StringComparison.OrdinalIgnoreCase) &&
                         parameterValue is string boolStringValue)
                {
                    if (bool.TryParse(boolStringValue, out var boolValue))
                    {
                        processedArguments[parameterName] = boolValue;
                        logger.LogInformation("Converted parameter '{ParameterName}' from string '{StringValue}' to boolean {BoolValue} for function {FunctionName}",
                            parameterName, boolStringValue, boolValue, functionName);
                    }
                    else
                    {
                        // If it can't be parsed as boolean, log warning and keep original value
                        logger.LogWarning("Could not parse parameter '{ParameterName}' value '{StringValue}' as boolean for function {FunctionName}, keeping original value",
                            parameterName, boolStringValue, functionName);
                        processedArguments[parameterName] = parameterValue;
                    }
                }
                else
                {
                    // For all other parameters, keep the original value
                    processedArguments[parameterName] = parameterValue;
                }
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error processing parameter '{ParameterName}' for function {FunctionName}, keeping original value", parameterName, functionName);
                processedArguments[parameterName] = parameterValue;
            }
        }

        return processedArguments;
    }
}