# Tutorial 3: Production to Adoption

## Overview

This tutorial demonstrates enterprise AI operations and continuous improvement for production agents. Building on Tutorials 1 and 2, it covers operational excellence, monitoring, optimization, and governance at scale.

## Features Covered

1. **Trace Data Collection & Debugging** - Application Insights integration for performance analysis
2. **Human Feedback Collection** - Collect and analyze user feedback for continuous improvement
3. **Model Fine-Tuning** - Prepare training data and create fine-tuning jobs
4. **Evaluation Insights** - Pattern detection and quality trend analysis
5. **AI Gateway Integration** - Azure API Management for centralized access control
6. **Continuous Monitoring** - Scheduled evaluations with Azure Functions
7. **Fleet-Wide Governance** - Compliance reporting across agent fleet
8. **Cost Optimization** - Cost analysis and optimization recommendations

## Prerequisites

- .NET 8.0 SDK
- Azure AI Foundry project from Tutorial 2
- Application Insights resource
- Azure API Management instance (optional)

## Setup

1. Copy `.env.template` to `.env` and configure:
   ```bash
   cp .env.template .env
   ```

2. Update `.env` with your Azure resources:
   ```
   PROJECT_ENDPOINT=https://your-project.eastus.api.azureml.ms
   AGENT_ID=your-agent-id
   APPINSIGHTS_INSTRUMENTATION_KEY=your-key
   APPINSIGHTS_CONNECTION_STRING=your-connection-string
   APIM_ENDPOINT=https://your-apim.azure-api.net
   MODEL_DEPLOYMENT_NAME=gpt-4o-mini
   ```

3. Restore packages:
   ```bash
   dotnet restore
   ```

## Running the Tutorial

```bash
dotnet run
```

The tutorial will execute all 8 production operations modules and generate comprehensive reports.

## Output Files

- `trace_analysis.json` - Performance and error analysis
- `feedback_summary.json` - User feedback aggregation
- `finetuning_config.json` - Fine-tuning job configuration
- `evaluation_insights.json` - Quality trends and patterns
- `gateway_config.json` - API Management policies
- `monitoring_schedule.json` - Scheduled evaluation config
- `governance_report.json` - Fleet compliance report
- `cost_report.json` - Cost analysis and optimization
- `tutorial_summary.json` - Overall execution summary

## Module Details

### 1. Trace Debugging (`TraceDebugging.cs`)
Collects and analyzes Application Insights traces to identify performance bottlenecks and error patterns.

### 2. Feedback Collection (`FeedbackCollection.cs`)
Aggregates user feedback (ratings, comments) and provides actionable insights for improvement.

### 3. Model Fine-Tuning (`ModelFineTuning.cs`)
Prepares training data from high-quality conversations and creates Azure OpenAI fine-tuning jobs.

### 4. Evaluation Insights (`EvaluationInsights.cs`)
Analyzes evaluation results to detect failure patterns and quality trends over time.

### 5. Gateway Integration (`GatewayIntegration.cs`)
Configures Azure API Management policies for rate limiting, caching, and access control.

### 6. Continuous Monitoring (`ContinuousMonitoring.cs`)
Sets up scheduled evaluations using Azure Functions for continuous quality monitoring.

### 7. Fleet Governance (`FleetGovernance.cs`)
Generates compliance reports across your agent fleet for governance oversight.

### 8. Cost Optimization (`CostOptimization.cs`)
Analyzes costs and provides recommendations for optimization (caching, model selection, etc.).

## Next Steps

1. Deploy monitoring functions to Azure Functions
2. Implement feedback collection in your UI
3. Review and act on optimization recommendations
4. Set up Application Insights dashboards
5. Configure cost alerts and budgets
6. Monitor fine-tuning job progress
7. Scale to additional agents and use cases

## Learn More

- [Azure AI Foundry Documentation](https://docs.microsoft.com/azure/ai-foundry)
- [Application Insights](https://docs.microsoft.com/azure/azure-monitor)
- [Azure API Management](https://docs.microsoft.com/azure/api-management)
- [Azure OpenAI Fine-Tuning](https://docs.microsoft.com/azure/ai-services/openai/how-to/fine-tuning)

## Troubleshooting

If you encounter issues:
1. Verify all environment variables are set correctly
2. Ensure Azure resources are properly configured
3. Check that you have appropriate permissions
4. Review Application Insights for detailed error traces

## Code Tags Reference

This tutorial includes code tags for documentation references:
- `<application_insights_setup>` - Application Insights configuration
- `<trace_analysis>` - Trace collection and analysis
- `<feedback_api>` - Feedback collection from production
- `<feedback_analysis>` - Feedback analysis and insights
- `<training_data_prep>` - Training data preparation
- `<finetuning_job>` - Fine-tuning job creation
- `<insight_generation>` - Evaluation insights generation
- `<apim_policies>` - API Management policy configuration
- `<quality_monitoring>` - Continuous monitoring setup
- `<compliance_reporting>` - Fleet governance reporting
- `<cost_analysis>` - Cost analysis and optimization
- `<authentication_setup>` - Azure authentication setup
- `<module_orchestration>` - Module execution orchestration
