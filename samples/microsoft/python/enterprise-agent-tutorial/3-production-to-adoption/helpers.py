"""
Helper utilities for Tutorial 3: Production to Adoption

Provides consistent formatting, output display, and utility functions
used across all modules in this tutorial.
"""

import json
from datetime import datetime
from typing import Dict, List, Any


def print_header(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"🚀 {title}")
    print("=" * 70)


def print_subheader(title: str):
    """Print a formatted subsection header."""
    print(f"\n{'─' * 50}")
    print(f"📊 {title}")
    print('─' * 50)


def print_success(message: str):
    """Print a success message."""
    print(f"✅ {message}")


def print_info(message: str):
    """Print an info message."""
    print(f"ℹ️  {message}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"⚠️  {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"❌ {message}")


def print_list_items(items: List[str], prefix: str = "  •"):
    """Print a bulleted list of items."""
    for item in items:
        print(f"{prefix} {item}")


def print_metric(name: str, value: Any, unit: str = ""):
    """Print a metric with formatting."""
    if unit:
        print(f"   {name}: {value} {unit}")
    else:
        print(f"   {name}: {value}")


def print_dict_tree(data: Dict, indent: int = 0):
    """Print a dictionary as a tree structure."""
    for key, value in data.items():
        if isinstance(value, dict):
            print("  " * indent + f"• {key}:")
            print_dict_tree(value, indent + 1)
        elif isinstance(value, list):
            print("  " * indent + f"• {key}: [{len(value)} items]")
        else:
            print("  " * indent + f"• {key}: {value}")


def save_json(data: Dict, filename: str):
    """Save data to a JSON file with pretty formatting."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print_success(f"Saved: {filename}")


def load_json(filename: str) -> Dict:
    """Load data from a JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print_warning(f"File not found: {filename}")
        return {}


def format_timestamp(timestamp: datetime = None) -> str:
    """Format a timestamp for display."""
    if timestamp is None:
        timestamp = datetime.now()
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a decimal as a percentage."""
    return f"{value * 100:.{decimals}f}%"


def format_currency(value: float, currency: str = "$") -> str:
    """Format a value as currency."""
    return f"{currency}{value:,.2f}"


def format_number(value: int) -> str:
    """Format a number with thousands separators."""
    return f"{value:,}"


def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """Calculate percentage change between two values."""
    if old_value == 0:
        return 0.0
    return ((new_value - old_value) / old_value) * 100


def truncate_string(text: str, max_length: int = 100) -> str:
    """Truncate a string to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def print_trace_summary(trace_data: Dict):
    """Print a formatted trace analysis summary."""
    print_subheader("Trace Analysis Summary")
    
    metrics = trace_data.get("metrics", {})
    print_metric("Total Traces", format_number(metrics.get("total_traces", 0)))
    print_metric("Average Latency", f"{metrics.get('avg_latency_ms', 0):.0f}ms")
    print_metric("P95 Latency", f"{metrics.get('p95_latency_ms', 0):.0f}ms")
    print_metric("Error Rate", format_percentage(metrics.get("error_rate", 0)))
    print_metric("Total Tokens", format_number(metrics.get("total_tokens", 0)))
    
    bottlenecks = trace_data.get("bottlenecks", [])
    if bottlenecks:
        print(f"\n🎯 Performance Bottlenecks:")
        for i, bottleneck in enumerate(bottlenecks[:5], 1):
            print(f"   {i}. {bottleneck['description']} ({bottleneck['impact']} impact)")


def print_feedback_summary(feedback_data: Dict):
    """Print a formatted feedback summary."""
    print_subheader("Feedback Summary")
    
    stats = feedback_data.get("statistics", {})
    total = stats.get("total_feedback", 0)
    positive = stats.get("positive_count", 0)
    negative = stats.get("negative_count", 0)
    
    print_metric("Total Feedback", format_number(total))
    if total > 0:
        print_metric("👍 Positive", f"{format_number(positive)} ({format_percentage(positive/total)})")
        print_metric("👎 Negative", f"{format_number(negative)} ({format_percentage(negative/total)})")
    
    suggestions = feedback_data.get("top_suggestions", [])
    if suggestions:
        print(f"\n📈 Top Improvement Suggestions:")
        for i, suggestion in enumerate(suggestions[:5], 1):
            print(f"   {i}. {suggestion['text']} ({suggestion['count']} mentions)")


def print_finetuning_summary(finetuning_data: Dict):
    """Print a formatted fine-tuning summary."""
    print_subheader("Fine-Tuning Summary")
    
    config = finetuning_data.get("config", {})
    print_metric("Training Examples", format_number(config.get("training_examples", 0)))
    print_metric("Validation Examples", format_number(config.get("validation_examples", 0)))
    print_metric("Base Model", config.get("base_model", "N/A"))
    
    job_id = finetuning_data.get("job_id")
    if job_id:
        print_metric("Job ID", job_id)
        print_metric("Status", finetuning_data.get("status", "pending"))


def print_evaluation_insights(insights_data: Dict):
    """Print formatted evaluation insights."""
    print_subheader("Evaluation Insights")
    
    patterns = insights_data.get("failure_patterns", [])
    if patterns:
        print(f"\n🔍 Failure Patterns Identified: {len(patterns)}")
        for i, pattern in enumerate(patterns[:3], 1):
            print(f"   {i}. {pattern['pattern']} (frequency: {pattern['frequency']}, impact: {pattern['impact']})")
    
    clusters = insights_data.get("topic_clusters", [])
    if clusters:
        print(f"\n📊 Topic Clusters: {len(clusters)}")
        for cluster in clusters[:3]:
            print(f"   • {cluster['cluster']}: {cluster['question_count']} questions, "
                  f"avg quality: {cluster['avg_quality_score']:.2f}")
    
    trends = insights_data.get("quality_trends", {})
    if trends:
        current = trends.get("current_month", 0)
        previous = trends.get("last_month", 0)
        change = trends.get("change_percent", 0)
        print(f"\n📈 Quality Trend: {format_percentage(current/100)} "
              f"({'+' if change > 0 else ''}{change:.1f}% vs last month)")


def print_gateway_summary(gateway_data: Dict):
    """Print a formatted gateway configuration summary."""
    print_subheader("Gateway Configuration")
    
    config = gateway_data.get("configuration", {})
    print_metric("Gateway Endpoint", config.get("endpoint", "N/A"))
    print_metric("Rate Limit", config.get("rate_limit", "N/A"))
    print_metric("Caching", "Enabled" if config.get("caching_enabled") else "Disabled")
    print_metric("Analytics", "Enabled" if config.get("analytics_enabled") else "Disabled")
    
    policies = gateway_data.get("policies", [])
    if policies:
        print(f"\n🔒 Applied Policies: {len(policies)}")
        print_list_items(policies)


def print_monitoring_summary(monitoring_data: Dict):
    """Print a formatted monitoring configuration summary."""
    print_subheader("Monitoring Configuration")
    
    schedule = monitoring_data.get("schedule", {})
    print("📅 Evaluation Schedule:")
    if schedule.get("hourly_checks", {}).get("enabled"):
        print(f"   • Hourly quality checks: {schedule['hourly_checks']['test_questions']} questions")
    if schedule.get("daily_reports", {}).get("enabled"):
        print(f"   • Daily reports to: {', '.join(schedule['daily_reports'].get('recipients', []))}")
    if schedule.get("weekly_analysis", {}).get("enabled"):
        print(f"   • Weekly deep-dive analysis")
    
    alerts = monitoring_data.get("alerts", [])
    if alerts:
        print(f"\n🚨 Configured Alerts: {len(alerts)}")
        for alert in alerts[:3]:
            print(f"   • {alert['name']}: {alert['condition']}")


def print_governance_summary(governance_data: Dict):
    """Print a formatted governance report summary."""
    print_subheader("Governance Report")
    
    stats = governance_data.get("statistics", {})
    print_metric("Total Agents", format_number(stats.get("total_agents", 0)))
    print_metric("Active Users", format_number(stats.get("active_users", 0)))
    print_metric("Departments", stats.get("departments", 0))
    print_metric("Compliance Rate", format_percentage(stats.get("compliance_rate", 0)))
    
    violations = governance_data.get("violations", [])
    if violations:
        print(f"\n🔒 Policy Violations: {len(violations)}")
        for violation in violations[:3]:
            print(f"   • {violation['type']}: {violation['description']} ({violation['status']})")


def print_cost_summary(cost_data: Dict):
    """Print a formatted cost analysis summary."""
    print_subheader("Cost Analysis")
    
    totals = cost_data.get("totals", {})
    total_cost = totals.get("total_cost", 0)
    print_metric("Total Cost (30 days)", format_currency(total_cost))
    
    breakdown = cost_data.get("breakdown", {})
    if breakdown:
        print("\n💰 Cost Breakdown:")
        for category, amount in breakdown.items():
            percentage = (amount / total_cost * 100) if total_cost > 0 else 0
            print(f"   • {category.replace('_', ' ').title()}: "
                  f"{format_currency(amount)} ({percentage:.1f}%)")
    
    optimizations = cost_data.get("optimization_opportunities", [])
    if optimizations:
        total_savings = sum(opt.get("potential_savings", 0) for opt in optimizations)
        print(f"\n🎯 Optimization Opportunities:")
        for opt in optimizations[:3]:
            savings = opt.get("potential_savings", 0)
            savings_pct = (savings / total_cost * 100) if total_cost > 0 else 0
            print(f"   • {opt['recommendation']}: "
                  f"Save {format_currency(savings)}/month ({savings_pct:.0f}%)")
        print(f"\n💡 Total Potential Savings: {format_currency(total_savings)}/month "
              f"({(total_savings/total_cost*100):.0f}%)")


def print_progress_bar(current: int, total: int, width: int = 50):
    """Print a progress bar."""
    if total == 0:
        return
    
    percentage = current / total
    filled = int(width * percentage)
    bar = "█" * filled + "░" * (width - filled)
    print(f"\r{bar} {percentage*100:.0f}% ({current}/{total})", end="", flush=True)


def create_summary_report(module_results: Dict[str, Dict]) -> Dict:
    """Create a comprehensive summary report from all module results."""
    return {
        "timestamp": format_timestamp(),
        "tutorial": "Production to Adoption",
        "modules": {
            "trace_debugging": {
                "status": "completed" if module_results.get("trace_debugging") else "skipped",
                "key_metrics": module_results.get("trace_debugging", {}).get("metrics", {})
            },
            "feedback_collection": {
                "status": "completed" if module_results.get("feedback_collection") else "skipped",
                "total_feedback": module_results.get("feedback_collection", {}).get("statistics", {}).get("total_feedback", 0)
            },
            "model_finetuning": {
                "status": "completed" if module_results.get("model_finetuning") else "skipped",
                "job_id": module_results.get("model_finetuning", {}).get("job_id")
            },
            "evaluation_insights": {
                "status": "completed" if module_results.get("evaluation_insights") else "skipped",
                "insights_count": len(module_results.get("evaluation_insights", {}).get("failure_patterns", []))
            },
            "gateway_integration": {
                "status": "completed" if module_results.get("gateway_integration") else "skipped",
                "endpoint": module_results.get("gateway_integration", {}).get("configuration", {}).get("endpoint")
            },
            "continuous_monitoring": {
                "status": "completed" if module_results.get("continuous_monitoring") else "skipped",
                "schedule_configured": bool(module_results.get("continuous_monitoring"))
            },
            "fleet_governance": {
                "status": "completed" if module_results.get("fleet_governance") else "skipped",
                "agents_monitored": module_results.get("fleet_governance", {}).get("statistics", {}).get("total_agents", 0)
            },
            "cost_optimization": {
                "status": "completed" if module_results.get("cost_optimization") else "skipped",
                "total_cost": module_results.get("cost_optimization", {}).get("totals", {}).get("total_cost", 0)
            }
        },
        "summary": {
            "modules_completed": sum(1 for m in module_results.values() if m),
            "total_modules": 8
        }
    }


def print_completion_summary(summary_report: Dict):
    """Print the final tutorial completion summary."""
    print_header("Tutorial Completion Summary")
    
    summary = summary_report.get("summary", {})
    completed = summary.get("modules_completed", 0)
    total = summary.get("total_modules", 8)
    
    print(f"\n✅ Completed {completed}/{total} modules successfully!\n")
    
    print("📁 Generated Artifacts:")
    artifacts = [
        "trace_analysis.json",
        "feedback_summary.json",
        "finetuning_config.json",
        "training_data.jsonl",
        "evaluation_insights.json",
        "gateway_policies.xml",
        "monitoring_schedule.json",
        "azure-function-monitoring.py",
        "governance_report.json",
        "cost_report.json",
        "optimization_recommendations.json"
    ]
    print_list_items(artifacts)
    
    print("\n🎯 Next Steps:")
    next_steps = [
        "Review all generated artifacts and configurations",
        "Deploy monitoring functions to Azure Functions",
        "Configure Application Insights dashboards",
        "Set up cost alerts and budgets",
        "Review and act on optimization recommendations",
        "Schedule regular governance reviews",
        "Monitor fine-tuning job progress",
        "Implement feedback collection in production UI"
    ]
    print_list_items(next_steps)
