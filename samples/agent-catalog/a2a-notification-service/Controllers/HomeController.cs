using A2A;
using A2A.Client.Configuration;
using A2A.Client.Services;
using A2A.Events;
using A2A.Models;
using A2A.Requests;
using a2a_notification_service.Models;
using Azure.Identity;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using Neuroglia;
using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace a2a_notification_service.Controllers;

public class HomeController : Controller
{
    private readonly ILogger<HomeController> _logger;

    private readonly string _endpoint;
    private readonly string _audience;
    private readonly string _apiVersion;
    private readonly IServer _server;


    public HomeController(ILogger<HomeController> logger, IServer server)
    {
        _logger = logger;
        _server = server;
        _endpoint = GetEnvVariableOrRaise("ENDPOINT");
        _audience = GetEnvVariableOrRaise("AUDIENCE");
        _apiVersion = GetEnvVariableOrRaise("API_VERSION");
        
    }

    /// <summary>
    /// Convenience method to get the environment variable or raise an exception.
    /// </summary>
    /// <param name="name">The name of environment variable.</param>
    /// <returns>The value of environment variable.</returns>
    /// <exception cref="InvalidOperationException"></exception>
    private static string GetEnvVariableOrRaise(string name)
    {
        string? variable = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrEmpty(variable))
        {
            throw new InvalidOperationException($"Please provide the environment variable {name}");
        }
        return variable;
    }

    /// <summary>
    /// Get the endpoint URI to be used by A2A protocal.
    /// </summary>
    /// <param name="agentId">The agent ID to send the request to.</param>
    /// <returns></returns>
    private string GetEndpoint(string agentId) => $"{_endpoint}/workflows/a2a/agents/{agentId}?api-version={_apiVersion}";

    /// <summary>
    /// Return the default page, in our case it is an UI of a Web Application.
    /// </summary>
    /// <returns>The main window.</returns>
    public IActionResult Index()
    {
        return View();
    }

    /// <summary>
    /// Return the privacy policy page.
    /// </summary>
    /// <returns>The view with privacy policy.</returns>
    public IActionResult Privacy()
    {
        return View();
    }

    /// <summary>
    /// Return the error page.
    /// </summary>
    /// <returns>The error page.</returns>
    [ResponseCache(Duration = 0, Location = ResponseCacheLocation.None, NoStore = true)]
    public IActionResult Error()
    {
        return View(new ErrorViewModel { RequestId = Activity.Current?.Id ?? HttpContext.TraceIdentifier });
    }

    /// <summary>
    /// The convenience method to create and authenticate the A2A client.
    /// </summary>
    /// <param name="agentID">The agent ID used by the client.</param>
    /// <returns>A2A client.</returns>
    private A2AProtocolHttpClient GetA2AClient(string agentID)
    {
        string agentUri = GetEndpoint(agentID);
        HttpClient httpClient = new();
        //DefaultAzureCredential tokenProvider = new ();
        AzureCliCredential tokenProvider = new();
        httpClient.DefaultRequestHeaders.Add("Authorization", $"Bearer {tokenProvider.GetToken(new Azure.Core.TokenRequestContext([_audience])).Token}");
        return new A2AProtocolHttpClient(Options.Create(
            new A2AProtocolClientOptions
            {
                Endpoint = new Uri(agentUri),
            }
        ), httpClient);
    }

    /// <summary>
    /// Add the results to the list of complete tasks.
    /// </summary>
    /// <param name="taskId">The task ID.</param>
    /// <param name="isFinal">If true the result was already received.</param>
    /// <param name="message">The message with the response or error.</param>
    private void AddToResults(string taskId, bool isFinal, string agentId, string message)
    {
        A2ATask task = new()
        {
            IsFinal=isFinal,
            Message=message,
            AgentId=agentId
        };
        HttpContext.Session.SetString(taskId, JsonSerializer.Serialize<A2ATask>(task));
    }

    /// <summary>
    /// Update the existing result.
    /// </summary>
    /// <param name="taskId">The task to be updated.</param>
    /// <param name="isFinal">If true the result was already received.</param>
    /// <param name="message">The message with the response or error.</param>
    private void UpdateResults(string taskId, bool isFinal, string message)
    {
        if(HttpContext.Session.TryGetValue(taskId, out byte[]? a2a) && a2a != null){
            A2ATask? task = JsonSerializer.Deserialize<A2ATask>(a2a);
            if (task != null)
            {
                task.IsFinal = isFinal;
                task.Message = message;
                HttpContext.Session.SetString(taskId, JsonSerializer.Serialize(task));
            }
        }
    }

    /// <summary>
    /// Process the request to create a task and return taskID in case of success.
    /// </summary>
    /// <param name="userMessage">The user message to send to agent.</param>
    /// <returns>The JSON with task ID in form {"task": "task id"}</returns>
    [HttpPost]
    public IActionResult CreateTask(UserMessageModel userMessage)
    {
        // Check the inputs.
        if (string.IsNullOrEmpty(userMessage.AgentId))
        {
            return BadRequest("The Agent Id is empty.");
        }
        if (string.IsNullOrEmpty(userMessage.Message))
        {
            return BadRequest("The Message is empty.");
        }
        string id = "<none>";
        // Create the task and return task ID.
        try
        {
            A2AProtocolHttpClient client = GetA2AClient(userMessage.AgentId);
            // Start the task.
            SendTaskRequest request = new ()
            {
                Params = new()
                {
                    Id = Guid.NewGuid().ToString("N"),
                    Message = new()
                    {
                        Role = A2A.MessageRole.User,
                        Parts =[new TextPart(userMessage.Message)]
                    }
                }
            };
            A2A.Models.Task? response = client.SendTaskAsync(request).Result.Result;
            if (response == null)
            {
                return StatusCode(500, "Unable to create task.");
            }
            if (response.Status.State == TaskState.Failed)
            {
                return StatusCode(500, "The task has failed.");
            }
            id = response.Id;
            // Cofigure the push notification for task.
            string? serverAddress = _server?.Features?.Get<IServerAddressesFeature>()?.Addresses.FirstOrDefault();
            if (serverAddress == null)
            {
                return StatusCode(500, "Unable to get the server address.");
            }
            SetTaskPushNotificationsRequest setPushNotifications = new()
            {
                Params = new()
                {
                    Id = id,
                    PushNotificationConfig = new()
                    {
                        Url = new($"{serverAddress}/Home/PushCallBack")
                    }
                }
            };

            // Debug code to test locally.
            StringBuilder sbResponse = new();
            foreach (var artifact in response?.Artifacts ?? Enumerable.Empty<Artifact>())
            {
                if (artifact.Parts != null)
                {
                    foreach (var part in artifact.Parts.OfType<TextPart>()) sbResponse.Append(part.Text);
                }
            }

            AddToResults(taskId: id, isFinal: true, agentId: userMessage.AgentId, message: sbResponse.ToString());
            ////////////////////////////////////

            //TaskPushNotificationConfiguration? pushConfig = client.SetTaskPushNotificationsAsync(setPushNotifications).Result.Result;
            //if (pushConfig == null)
            //{
            //    return StatusCode(500, "Unable to create a push notification for task.");
            //}

        }
        catch(Exception e)
        {
            return StatusCode(500, e.Message);
        }
        return Json(new
        {
            task = id
        });
    }

    /// <summary>
    /// Process the request for the task result.
    /// </summary>
    /// <param name="taskId">The ID of a task to check.</param>
    /// <returns>The JSON in form {"status": "running|finished", "message": "Message content."}</returns>
    [HttpGet]
    public IActionResult GetTaskResult(string taskId)
    {
        string? taskResult = HttpContext.Session.GetString(taskId);
        if (string.IsNullOrEmpty(taskResult))
        {
            return NotFound($"The task {taskId} was not found.");
        }
        HttpContext.Session.Remove(taskId);
        return Json(JsonSerializer.Deserialize<A2ATask>(taskResult));
    }

    /// <summary>
    /// Check the pushback URL. It is a probe, required by A2A. Accepts the validationToken and return it back.
    /// </summary>
    /// <param name="validationToken">The validation token.</param>
    /// <returns>The validationToken without change.</returns>
    [HttpGet]
    public IActionResult PushCallBack(string validationToken)
    {
        if (string.IsNullOrEmpty(validationToken))
            return BadRequest("Please provide the validation token.");
        return Ok(validationToken);
    }

    /// <summary>
    /// Process the pushback request from the service.
    /// If the task completed, remove it from the list of running tasks and place the returned content
    /// or error to the list of completed tasks with the same ID. 
    /// </summary>
    /// <param name="taskEvent">The task event object.</param>
    /// <returns>If the task ID is not present, return 400, otherwise return 200.</returns>
    [HttpPost]
    public IActionResult PushCallBack(TaskStatusUpdateEvent taskEvent)
    {
        string agentId;
        if (HttpContext.Session.TryGetValue(taskEvent.Id, out byte[]? agent_id_byte))
        {
            agentId = Encoding.Default.GetString(agent_id_byte);
        }
        else
        {
            return NotFound($"The task {taskEvent.Id} was not found.");
        }
        if (taskEvent.Status.State == TaskState.Completed)
        {
            A2AProtocolHttpClient client = GetA2AClient(agentId);
            GetTaskRequest getRequest = new()
            {
                Id= taskEvent.Id
            };
            A2A.Models.Task? response = client.GetTaskAsync(getRequest).Result.Result;
            StringBuilder sbResponse = new();
            foreach (var artifact in response?.Artifacts ?? Enumerable.Empty<Artifact>())
            {
                if (artifact.Parts != null)
                {
                    foreach (var part in artifact.Parts.OfType<TextPart>()) sbResponse.Append(part.Text);
                }
            }

            UpdateResults(taskEvent.Id, taskEvent.Final, sbResponse.ToString());
        }
        else if (taskEvent.Status.State == TaskState.Failed)
        {
            UpdateResults(taskEvent.Id, taskEvent.Final, $"Error! Message: {taskEvent.Status.Message}");
        }
        else if (taskEvent.Status.State == TaskState.InputRequired)
        {
            UpdateResults(taskEvent.Id, true, $"Error! The task is in \"Input required\" state, it is not supported yet.");
            if (HttpContext.Session.TryGetValue(taskEvent.Id, out byte[]? a2a) && a2a != null)
            {
                A2ATask? task = JsonSerializer.Deserialize<A2ATask>(a2a);
                if (task != null)
                {
                    A2AProtocolHttpClient client = GetA2AClient(task.AgentId ?? "");
                    CancelTaskRequest cancelRequest = new()
                    {
                        Id = taskEvent.Id
                    };
                    _ = client.CancelTaskAsync(cancelRequest).Result;
                }
            }
        }
        return Ok();
    }
}
