# Stage 3: Production to Adoption

This is the third and final stage of the Azure AI Foundry Enterprise Agent Tutorial series. This stage focuses on production operations capabilities that enable successful agent adoption at enterprise scale.

## Overview

After deploying your agent to production (Stage 2), this stage demonstrates how to:
- Monitor and improve agent performance using production data
- Collect and analyze user feedback
- Fine-tune models based on real-world usage
- Implement governance and cost controls
- Ensure continuous quality and compliance

## What You'll Learn

This tutorial covers eight critical production operations capabilities:

### 1. Debug & Improve Using Trace Data
- Set up Application Insights for comprehensive trace collection
- Analyze traces to identify performance bottlenecks
- Generate actionable recommendations for improvement
- Export trace data for offline analysis

### 2. Human Feedback Collection
- Implement feedback collection APIs
- Store and analyze user feedback from production
- Identify improvement areas from user sentiment
- Export feedback data for agent developers

### 3. Model Fine-Tuning
- Prepare training data from production feedback and traces
- Submit fine-tuning jobs to Azure OpenAI
- Monitor fine-tuning progress
- Validate and deploy fine-tuned models

### 4. Evaluation Insights
- Analyze offline evaluation results
- Detect performance patterns and failure modes
- Track improvement trends over time
- Generate insights for targeted improvements

### 5. AI Gateway Integration
- Configure Azure API Management as an AI gateway
- Implement rate limiting and throttling
- Add authentication and authorization
- Enable comprehensive request/response logging

### 6. Continuous Quality Monitoring
- Set up automated evaluation pipelines
- Schedule periodic quality checks
- Monitor performance metrics in real-time
- Configure alerts for quality degradation

### 7. Fleet Governance
- Track agent usage across the entire fleet
- Implement access controls and permissions
- Generate compliance reports
- Audit agent interactions

### 8. Cost Optimization
- Monitor token usage and API costs
- Analyze cost trends by agent and user
- Identify optimization opportunities
- Set up budget alerts and controls

## Prerequisites

- Completion of [Stage 1: Idea to Prototype](../1-idea-to-prototype/README.md)
- Completion of [Stage 2: Prototype to Production](../2-prototype-to-production/README.md)
- Java Development Kit (JDK) 17 or later
- Maven 3.6 or later
- An Azure AI Foundry project with:
  - Azure OpenAI connection configured
  - Application Insights enabled
  - (Optional) Azure API Management instance

## Setup Instructions

### 1. Install Dependencies

The project uses Maven for dependency management. All required dependencies are specified in `pom.xml`:

```bash
mvn clean install
```

### 2. Configure Environment Variables

Copy `.env.template` to `.env` and fill in your Azure resource details:

```bash
cp .env.template .env
```

Edit `.env` with your values:

```properties
# Required
PROJECT_ENDPOINT=https://your-project.api.azureml.ms
SUBSCRIPTION_ID=your-subscription-id
RESOURCE_GROUP_NAME=your-resource-group
PROJECT_NAME=your-project-name
CONNECTION_NAME=your-aoai-connection-name
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...

# Optional (for gateway integration)
APIM_ENDPOINT=https://your-apim-instance.azure-api.net
```

### 3. Authenticate with Azure

The sample uses `DefaultAzureCredential` which supports multiple authentication methods:

**Azure CLI (Recommended for local development):**
```bash
az login
```

**Other supported methods:**
- Managed Identity (automatic in Azure)
- Environment variables (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`)
- Visual Studio Code (sign in through VS Code)
- Azure PowerShell

### 4. Run the Sample

```bash
mvn exec:java -Dexec.mainClass="com.microsoft.azure.samples.productiontoadoption.Main"
```

## Project Structure

```
3-production-to-adoption/
├── src/main/java/com/microsoft/azure/samples/productiontoadoption/
│   ├── Main.java                      # Main orchestrator
│   ├── Helpers.java                   # Utility functions
│   ├── TraceDebugging.java           # Module 1: Trace analysis
│   ├── FeedbackCollection.java       # Module 2: Feedback collection
│   ├── ModelFineTuning.java          # Module 3: Fine-tuning
│   └── EvaluationInsights.java       # Modules 4-8: Insights, gateway, monitoring, governance, costs
├── pom.xml                            # Maven project configuration
├── .env.template                      # Environment variable template
└── README.md                          # This file
```

## Module Details

### Module 1: Trace Debugging (`TraceDebugging.java`)

Demonstrates Application Insights integration for trace collection and analysis:

```java
// Set up Application Insights
TraceDebugging traceDebugging = new TraceDebugging(projectClient, appInsightsConnectionString);
traceDebugging.setupApplicationInsights();

// Analyze collected traces
Map<String, Object> analysis = traceDebugging.analyzeTraces(Duration.ofHours(24));

// Generate recommendations
List<String> recommendations = traceDebugging.generateRecommendations(analysis);
```

**Key Features:**
- Application Insights configuration
- Trace data analysis
- Performance issue identification
- Actionable recommendations

### Module 2: Feedback Collection (`FeedbackCollection.java`)

Implements user feedback collection and analysis:

```java
// Set up feedback collection
FeedbackCollection feedbackCollection = new FeedbackCollection(projectClient);
feedbackCollection.setupFeedbackCollection();

// Collect feedback from users
feedbackCollection.collectFeedback(agentId, conversationId, rating, comments, userId);

// Analyze feedback patterns
Map<String, Object> analysis = feedbackCollection.analyzeFeedback(Duration.ofDays(7));
```

**Key Features:**
- Feedback API endpoints
- Sentiment analysis
- Pattern detection
- Developer insights

### Module 3: Model Fine-Tuning (`ModelFineTuning.java`)

Shows how to fine-tune models using production data:

```java
// Prepare training data
ModelFineTuning modelFineTuning = new ModelFineTuning(projectClient, connectionName);
Map<String, Object> trainingData = modelFineTuning.prepareTrainingData(feedbackData, traceData);

// Submit fine-tuning job
String jobId = modelFineTuning.submitFineTuningJob("gpt-4o-mini", trainingData);

// Monitor and deploy
Map<String, Object> status = modelFineTuning.monitorFineTuningJob(jobId);
modelFineTuning.deployFineTunedModel(fineTunedModel);
```

**Key Features:**
- Training data preparation
- Fine-tuning job submission
- Progress monitoring
- Model validation and deployment

### Module 4: Evaluation Insights (`EvaluationInsights.java`)

Generates insights from evaluation results:

```java
// Analyze evaluation results
EvaluationInsights evaluationInsights = new EvaluationInsights(projectClient);
Map<String, Object> insights = evaluationInsights.generateInsights(evaluationResults);
```

**Key Features:**
- Pattern detection
- Performance trend analysis
- Failure mode identification
- Targeted recommendations

### Module 5: Gateway Integration (`GatewayIntegration` class in `EvaluationInsights.java`)

Configures Azure API Management as an AI gateway:

```java
// Configure gateway policies
GatewayIntegration gatewayIntegration = new GatewayIntegration(projectClient, apimEndpoint);
gatewayIntegration.configureGatewayPolicies();
```

**Key Features:**
- Rate limiting
- Authentication/authorization
- Request/response logging
- Caching policies

### Module 6: Continuous Monitoring (`ContinuousMonitoring` class in `EvaluationInsights.java`)

Sets up automated quality monitoring:

```java
// Set up continuous monitoring
ContinuousMonitoring continuousMonitoring = new ContinuousMonitoring(projectClient);
continuousMonitoring.setupQualityMonitoring();
```

**Key Features:**
- Scheduled evaluations
- Real-time metrics
- Automated alerts
- Quality thresholds

### Module 7: Fleet Governance (`FleetGovernance` class in `EvaluationInsights.java`)

Implements governance and compliance:

```java
// Generate compliance report
FleetGovernance fleetGovernance = new FleetGovernance(projectClient);
Map<String, Object> report = fleetGovernance.generateComplianceReport();
```

**Key Features:**
- Fleet-wide monitoring
- Access control auditing
- Compliance reporting
- Policy enforcement

### Module 8: Cost Optimization (`CostOptimization` class in `EvaluationInsights.java`)

Tracks and optimizes costs:

```java
// Analyze costs
CostOptimization costOptimization = new CostOptimization(projectClient);
Map<String, Object> analysis = costOptimization.analyzeCosts(30);
```

**Key Features:**
- Token usage tracking
- Cost trend analysis
- Optimization recommendations
- Budget alerts

## Code Tags Reference

The sample includes tagged code snippets demonstrating key features:

| Tag | Module | Description |
|-----|--------|-------------|
| `<authentication_setup>` | Main | Azure authentication setup |
| `<module_orchestration>` | Main | Module execution flow |
| `<application_insights_setup>` | TraceDebugging | Application Insights configuration |
| `<trace_analysis>` | TraceDebugging | Trace data analysis |
| `<feedback_api>` | FeedbackCollection | Feedback API setup |
| `<feedback_analysis>` | FeedbackCollection | Feedback pattern analysis |
| `<training_data_prep>` | ModelFineTuning | Training data preparation |
| `<finetuning_job>` | ModelFineTuning | Fine-tuning job submission |
| `<insight_generation>` | EvaluationInsights | Evaluation insights generation |
| `<apim_policies>` | GatewayIntegration | API Management policies |
| `<quality_monitoring>` | ContinuousMonitoring | Quality monitoring setup |
| `<compliance_reporting>` | FleetGovernance | Compliance report generation |
| `<cost_analysis>` | CostOptimization | Cost analysis and optimization |

## Best Practices

### Trace Collection
- Enable Application Insights from day one
- Collect comprehensive telemetry (requests, dependencies, exceptions)
- Set appropriate sampling rates for high-volume scenarios
- Use structured logging for better analysis

### Feedback Management
- Make feedback collection easy and non-intrusive
- Collect both quantitative (ratings) and qualitative (comments) feedback
- Act on feedback promptly to show users their input matters
- Protect user privacy and follow data governance policies

### Fine-Tuning
- Only fine-tune when you have sufficient high-quality data (hundreds of examples)
- Validate fine-tuned models thoroughly before production deployment
- Monitor fine-tuned model performance continuously
- Keep base models as fallback options

### Monitoring & Governance
- Implement continuous monitoring from the start
- Set up alerts for critical metrics (quality, costs, errors)
- Review governance reports regularly
- Automate compliance checks where possible

### Cost Management
- Monitor costs daily, especially during initial deployment
- Set up budget alerts to prevent surprises
- Implement caching to reduce redundant API calls
- Use appropriate model sizes for different tasks

## Troubleshooting

### Authentication Issues
```
Error: DefaultAzureCredential failed to retrieve a token
```
**Solution:** Ensure you're logged in via Azure CLI (`az login`) or have appropriate environment variables set.

### Application Insights Connection
```
Error: Failed to connect to Application Insights
```
**Solution:** Verify your `APPLICATIONINSIGHTS_CONNECTION_STRING` is correct and the resource exists.

### Fine-Tuning Job Failures
```
Error: Fine-tuning job failed
```
**Solution:** Check training data format, ensure sufficient examples, and verify Azure OpenAI quota.

## Next Steps

After completing this tutorial:

1. **Implement in Production:** Apply these patterns to your production agents
2. **Automate Monitoring:** Set up automated pipelines for continuous monitoring
3. **Establish Governance:** Define and enforce policies across your agent fleet
4. **Optimize Costs:** Regularly review and optimize based on usage patterns
5. **Iterate Continuously:** Use production data to continuously improve your agents

## Additional Resources

- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-studio/)
- [Azure AI Projects SDK for Java](https://learn.microsoft.com/java/api/overview/azure/ai-projects-readme)
- [Application Insights Overview](https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview)
- [Azure API Management](https://learn.microsoft.com/azure/api-management/)
- [Azure OpenAI Fine-tuning](https://learn.microsoft.com/azure/ai-services/openai/how-to/fine-tuning)
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/)

## Support

For issues or questions:
- Check the [troubleshooting section](#troubleshooting)
- Review [Azure AI Foundry documentation](https://learn.microsoft.com/azure/ai-studio/)
- Open an issue in the repository

## License

This sample code is provided under the MIT License. See LICENSE file for details.
