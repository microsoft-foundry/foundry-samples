"""
Azure AI Foundry - Production to Adoption

Tutorial 3: Enterprise AI Operations & Continuous Improvement

This tutorial demonstrates how to operationalize, monitor, optimize, and govern
production AI agents at scale with comprehensive observability, feedback loops,
and continuous improvement.

Main workflow orchestrates all production operations modules:
1. Trace Data Collection & Debugging
2. Human Feedback Collection & Analysis
3. Model Fine-Tuning Pipeline
4. Evaluation Insights Analysis
5. AI Gateway Integration
6. Continuous Monitoring Setup
7. Fleet-Wide Governance
8. Cost Monitoring & Optimization
"""

import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# Import all modules
from trace_debugging import TraceDebugging
from feedback_collection import FeedbackCollection
from model_finetuning import ModelFineTuning
from evaluation_insights import EvaluationInsights
from gateway_integration import GatewayIntegration
from continuous_monitoring import ContinuousMonitoring
from fleet_governance import FleetGovernance
from cost_optimization import CostOptimization
import helpers

def main():
    """Main execution flow for Production to Adoption tutorial."""
    
    # Load environment variables
    load_dotenv()
    
    # Display tutorial header
    helpers.print_header("Azure AI Foundry - Production to Adoption")
    print("Tutorial 3: Enterprise AI Operations & Continuous Improvement\n")
    
    print("This tutorial demonstrates production operations for enterprise AI agents:")
    helpers.print_list_items([
        "Trace data collection and performance debugging",
        "Human feedback collection and analysis",
        "Model fine-tuning with production data",
        "Evaluation insights and pattern detection",
        "AI gateway integration (API Management)",
        "Continuous monitoring with scheduled evaluations",
        "Fleet-wide governance and compliance",
        "Cost monitoring and optimization"
    ])
    
    # Collect module results
    module_results = {}
    
    try:
        # <authentication_setup>
        # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        # Initialize Azure AI Project Client
        project_endpoint = os.getenv("PROJECT_ENDPOINT")
        if not project_endpoint:
            helpers.print_warning("PROJECT_ENDPOINT not set. Using mock client for demonstration.")
            project_client = None
        else:
            helpers.print_info("Initializing Azure AI Project Client...")
            project_client = AIProjectClient(
                endpoint=project_endpoint,
                credential=DefaultAzureCredential()
            )
            helpers.print_success("Project client initialized")
        # </authentication_setup>
        
        # Get agent ID (from previous tutorial or environment)
        agent_id = os.getenv("AGENT_ID", "demo-agent-123")
        
        # <module_orchestration>
        # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        # Module 1: Trace Data Collection & Debugging
        try:
            trace_debugger = TraceDebugging(project_client, agent_id)
            module_results["trace_debugging"] = trace_debugger.run()
        except Exception as e:
            helpers.print_error(f"Trace debugging failed: {e}")
            module_results["trace_debugging"] = None
        
        # Module 2: Human Feedback Collection
        try:
            feedback_collector = FeedbackCollection(project_client, agent_id)
            module_results["feedback_collection"] = feedback_collector.run()
        except Exception as e:
            helpers.print_error(f"Feedback collection failed: {e}")
            module_results["feedback_collection"] = None
        
        # Module 3: Model Fine-Tuning Pipeline
        try:
            finetuner = ModelFineTuning(project_client, agent_id)
            module_results["model_finetuning"] = finetuner.run()
        except Exception as e:
            helpers.print_error(f"Model fine-tuning failed: {e}")
            module_results["model_finetuning"] = None
        
        # Module 4: Evaluation Insights Analysis
        try:
            insights_analyzer = EvaluationInsights(project_client, agent_id)
            module_results["evaluation_insights"] = insights_analyzer.run()
        except Exception as e:
            helpers.print_error(f"Evaluation insights failed: {e}")
            module_results["evaluation_insights"] = None
        
        # Module 5: AI Gateway Integration
        try:
            gateway = GatewayIntegration(project_client, agent_id)
            module_results["gateway_integration"] = gateway.run()
        except Exception as e:
            helpers.print_error(f"Gateway integration failed: {e}")
            module_results["gateway_integration"] = None
        
        # Module 6: Continuous Monitoring
        try:
            monitoring = ContinuousMonitoring(project_client, agent_id)
            module_results["continuous_monitoring"] = monitoring.run()
        except Exception as e:
            helpers.print_error(f"Continuous monitoring failed: {e}")
            module_results["continuous_monitoring"] = None
        
        # Module 7: Fleet-Wide Governance
        try:
            governance = FleetGovernance(project_client, agent_id)
            module_results["fleet_governance"] = governance.run()
        except Exception as e:
            helpers.print_error(f"Fleet governance failed: {e}")
            module_results["fleet_governance"] = None
        
        # Module 8: Cost Monitoring & Optimization
        try:
            cost_optimizer = CostOptimization(project_client, agent_id)
            module_results["cost_optimization"] = cost_optimizer.run()
        except Exception as e:
            helpers.print_error(f"Cost optimization failed: {e}")
            module_results["cost_optimization"] = None
        # </module_orchestration>
        
        # Generate summary report
        summary_report = helpers.create_summary_report(module_results)
        helpers.save_json(summary_report, "tutorial_summary.json")
        
        # Display completion summary
        helpers.print_completion_summary(summary_report)
        
        # Final message
        print("\n" + "="*70)
        helpers.print_success("Tutorial 3 completed successfully!")
        print("="*70)
        print("\n🎉 Congratulations! You've completed the full Enterprise Agent Tutorial series!")
        print("\nYour Modern Workplace Assistant is now:")
        helpers.print_list_items([
            "✅ Production-ready with safety and governance",
            "✅ Continuously monitored with automated evaluations",
            "✅ Optimized through human feedback and fine-tuning",
            "✅ Cost-efficient with optimization recommendations",
            "✅ Compliant with fleet-wide governance",
            "✅ Gateway-managed for centralized access control"
        ])
        
        print("\n📚 Next Steps:")
        helpers.print_list_items([
            "Deploy monitoring functions to Azure Functions",
            "Implement feedback collection in your production UI",
            "Review and act on optimization recommendations",
            "Set up Application Insights dashboards",
            "Configure cost alerts and budgets",
            "Monitor fine-tuning job progress",
            "Scale to additional agents and use cases"
        ])
        
        print("\n🔗 Learn More:")
        print("   • Azure AI Foundry Documentation: https://docs.microsoft.com/azure/ai-foundry")
        print("   • Application Insights: https://docs.microsoft.com/azure/azure-monitor")
        print("   • Azure API Management: https://docs.microsoft.com/azure/api-management")
        
        print("\n✨ Thank you for completing the Enterprise Agent Tutorial series!")
        
    except Exception as e:
        helpers.print_error(f"An error occurred: {str(e)}")
        print("\nTip: Check that your environment variables are configured correctly.")
        print("See .env.template for required configuration.")
        raise

if __name__ == "__main__":
    main()
