"""
Trace Data Collection & Debugging Module

This module demonstrates how to collect and analyze production traces from
Azure Application Insights to identify performance bottlenecks and improve
agent performance.

Key Features:
- Application Insights integration
- Trace collection and analysis
- Performance metric calculation
- Bottleneck identification
- Error pattern detection
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List
import random
import helpers

class TraceDebugging:
    """Handles trace collection and performance analysis."""
    
    def __init__(self, project_client, agent_id: str):
        """Initialize trace debugging with project client and agent ID."""
        self.project_client = project_client
        self.agent_id = agent_id
        self.connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
        
    # <application_insights_setup>
    # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    def setup_application_insights(self) -> Dict:
        """
        Configure Application Insights integration for trace collection.
        
        In production, this would:
        1. Initialize Application Insights client
        2. Configure sampling rates
        3. Set up custom dimensions
        4. Enable distributed tracing
        
        Returns:
            Configuration dictionary
        """
        config = {
            "connection_string": self.connection_string[:50] + "..." if self.connection_string else "Not configured",
            "sampling_rate": 1.0,  # 100% for demo, adjust in production
            "enable_distributed_tracing": True,
            "custom_dimensions": [
                "agent_id",
                "user_id",
                "conversation_id",
                "model_name",
                "tool_name"
            ],
            "retention_days": 90
        }
        
        return config
    # </application_insights_setup>
    
    def collect_production_traces(self, days: int = 7) -> List[Dict]:
        """
        Collect production traces from Application Insights.
        
        In production, this would query Application Insights using:
        - azure.monitor.query library
        - KQL (Kusto Query Language)
        - Time range filters
        
        For demo, generates synthetic trace data.
        
        Args:
            days: Number of days of traces to collect
            
        Returns:
            List of trace dictionaries
        """
        helpers.print_info(f"Collecting traces from last {days} days...")
        
        # Generate synthetic traces for demonstration
        traces = []
        num_traces = random.randint(1000, 1500)
        
        for i in range(num_traces):
            trace = {
                "trace_id": f"trace-{i:06d}",
                "timestamp": (datetime.now() - timedelta(days=random.randint(0, days))).isoformat(),
                "agent_id": self.agent_id,
                "operation": random.choice(["chat_completion", "tool_execution", "retrieval"]),
                "duration_ms": random.gauss(2345, 800),  # Normal distribution around 2345ms
                "status": random.choice(["success"] * 95 + ["error"] * 5),  # 95% success rate
                "token_usage": {
                    "prompt_tokens": random.randint(100, 500),
                    "completion_tokens": random.randint(50, 300),
                    "total_tokens": 0  # Will calculate
                },
                "model": os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"),
                "user_id": f"user{random.randint(1, 50)}@company.com",
                "conversation_id": f"conv-{random.randint(1000, 9999)}"
            }
            trace["token_usage"]["total_tokens"] = (
                trace["token_usage"]["prompt_tokens"] + 
                trace["token_usage"]["completion_tokens"]
            )
            
            # Add tool execution time for tool operations
            if trace["operation"] == "tool_execution":
                trace["tool_name"] = random.choice(["SharePoint", "MicrosoftLearn", "WebSearch"])
                trace["tool_duration_ms"] = random.gauss(500, 200)
            
            traces.append(trace)
        
        helpers.print_success(f"Collected {len(traces)} traces")
        return traces
    
    # <trace_analysis>
    # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    def analyze_traces(self, traces: List[Dict]) -> Dict:
        """
        Analyze collected traces to extract performance insights.
        
        Calculates:
        - Average and percentile latencies
        - Error rates
        - Token usage statistics
        - Performance bottlenecks
        
        Args:
            traces: List of trace dictionaries
            
        Returns:
            Analysis results dictionary
        """
        helpers.print_info("Analyzing trace data...")
        
        if not traces:
            return {"error": "No traces to analyze"}
        
        # Calculate latency metrics
        latencies = [t["duration_ms"] for t in traces if t["duration_ms"] > 0]
        latencies.sort()
        
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p50_latency = latencies[int(len(latencies) * 0.50)] if latencies else 0
        p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99_latency = latencies[int(len(latencies) * 0.99)] if latencies else 0
        
        # Calculate error rate
        errors = sum(1 for t in traces if t["status"] == "error")
        error_rate = errors / len(traces) if traces else 0
        
        # Calculate token usage
        total_tokens = sum(t["token_usage"]["total_tokens"] for t in traces)
        avg_tokens_per_request = total_tokens / len(traces) if traces else 0
        
        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(traces, p95_latency)
        
        # Analyze by operation type
        operations = {}
        for trace in traces:
            op = trace["operation"]
            if op not in operations:
                operations[op] = {"count": 0, "total_duration": 0, "errors": 0}
            operations[op]["count"] += 1
            operations[op]["total_duration"] += trace["duration_ms"]
            if trace["status"] == "error":
                operations[op]["errors"] += 1
        
        for op in operations:
            operations[op]["avg_duration"] = (
                operations[op]["total_duration"] / operations[op]["count"]
            )
            operations[op]["error_rate"] = (
                operations[op]["errors"] / operations[op]["count"]
            )
        
        analysis = {
            "collection_period": f"Last {len(set(t['timestamp'][:10] for t in traces))} days",
            "metrics": {
                "total_traces": len(traces),
                "avg_latency_ms": round(avg_latency, 2),
                "p50_latency_ms": round(p50_latency, 2),
                "p95_latency_ms": round(p95_latency, 2),
                "p99_latency_ms": round(p99_latency, 2),
                "error_rate": round(error_rate, 4),
                "total_tokens": total_tokens,
                "avg_tokens_per_request": round(avg_tokens_per_request, 2)
            },
            "bottlenecks": bottlenecks,
            "operations": operations,
            "recommendations": self._generate_recommendations(
                avg_latency, error_rate, bottlenecks, operations
            )
        }
        
        return analysis
    # </trace_analysis>
    
    def _identify_bottlenecks(self, traces: List[Dict], threshold_ms: float) -> List[Dict]:
        """Identify performance bottlenecks in traces."""
        bottlenecks = []
        
        # Check for slow operations
        slow_operations = [t for t in traces if t["duration_ms"] > threshold_ms]
        if len(slow_operations) > len(traces) * 0.05:  # More than 5% are slow
            bottlenecks.append({
                "type": "slow_operations",
                "description": f"{len(slow_operations)} operations exceed P95 latency",
                "impact": "high",
                "affected_traces": len(slow_operations)
            })
        
        # Check for tool execution delays
        tool_traces = [t for t in traces if t["operation"] == "tool_execution"]
        if tool_traces:
            avg_tool_duration = sum(t.get("tool_duration_ms", 0) for t in tool_traces) / len(tool_traces)
            if avg_tool_duration > 1000:  # More than 1 second
                bottlenecks.append({
                    "type": "slow_tool_execution",
                    "description": f"Average tool execution time: {avg_tool_duration:.0f}ms",
                    "impact": "medium",
                    "affected_traces": len(tool_traces)
                })
        
        # Check for high token usage
        high_token_traces = [
            t for t in traces 
            if t["token_usage"]["total_tokens"] > 2000
        ]
        if high_token_traces:
            bottlenecks.append({
                "type": "high_token_usage",
                "description": f"{len(high_token_traces)} traces use >2000 tokens",
                "impact": "medium",
                "affected_traces": len(high_token_traces)
            })
        
        return bottlenecks
    
    def _generate_recommendations(
        self, 
        avg_latency: float, 
        error_rate: float,
        bottlenecks: List[Dict],
        operations: Dict
    ) -> List[str]:
        """Generate optimization recommendations based on analysis."""
        recommendations = []
        
        if avg_latency > 3000:
            recommendations.append(
                "Consider optimizing prompt length to reduce latency"
            )
        
        if error_rate > 0.02:  # More than 2% errors
            recommendations.append(
                "Investigate error patterns and implement retry logic"
            )
        
        if any(b["type"] == "slow_tool_execution" for b in bottlenecks):
            recommendations.append(
                "Implement caching for frequently accessed tool results"
            )
        
        if any(b["type"] == "high_token_usage" for b in bottlenecks):
            recommendations.append(
                "Optimize prompts to reduce token usage and costs"
            )
        
        # Check operation-specific recommendations
        for op, metrics in operations.items():
            if metrics["error_rate"] > 0.05:
                recommendations.append(
                    f"High error rate in {op} operations - review implementation"
                )
        
        if not recommendations:
            recommendations.append("Performance is within acceptable ranges")
        
        return recommendations
    
    def run(self) -> Dict:
        """Execute complete trace debugging workflow."""
        helpers.print_header("Trace Data Collection & Debugging")
        
        # Setup Application Insights
        helpers.print_info("Configuring Application Insights integration...")
        config = self.setup_application_insights()
        
        # Collect traces
        traces = self.collect_production_traces(days=7)
        
        # Analyze traces
        analysis = self.analyze_traces(traces)
        
        # Display results
        helpers.print_trace_summary(analysis)
        
        # Save results
        result = {
            "configuration": config,
            "analysis": analysis,
            "timestamp": helpers.format_timestamp()
        }
        
        helpers.save_json(result, "trace_analysis.json")
        
        return analysis


def main():
    """Standalone execution for testing."""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Mock project client for testing
    class MockProjectClient:
        pass
    
    project_client = MockProjectClient()
    agent_id = os.getenv("AGENT_ID", "agent-test-123")
    
    debugger = TraceDebugging(project_client, agent_id)
    debugger.run()


if __name__ == "__main__":
    main()
