"""
Human Feedback Collection Module

This module demonstrates how to collect, aggregate, and analyze human feedback
from production users to drive continuous improvement of AI agents.

Key Features:
- Feedback API implementation
- Rating aggregation (thumbs up/down)
- Detailed feedback collection
- Topic extraction and analysis
- Export capabilities for training data
"""

import os
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List
import random
import helpers

class FeedbackCollection:
    """Handles human feedback collection and analysis."""
    
    def __init__(self, project_client, agent_id: str):
        """Initialize feedback collection with project client and agent ID."""
        self.project_client = project_client
        self.agent_id = agent_id
    
    # <feedback_api>
    # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    def collect_feedback_from_production(self, days: int = 30) -> List[Dict]:
        """
        Collect feedback from production users.
        
        In production, this would:
        1. Query feedback database or storage
        2. Filter by date range and agent ID
        3. Include user metadata
        
        For demo, generates synthetic feedback data.
        
        Args:
            days: Number of days of feedback to collect
            
        Returns:
            List of feedback dictionaries
        """
        helpers.print_info(f"Collecting user feedback from last {days} days...")
        
        # Generate synthetic feedback for demonstration
        feedback_list = []
        num_feedback = random.randint(700, 900)
        
        feedback_templates = {
            "positive": [
                "Great response, very helpful!",
                "Exactly what I needed, thank you",
                "Clear and accurate information",
                "Fast and comprehensive answer",
                "Very useful, solved my problem"
            ],
            "negative": [
                "Response was too slow",
                "Could provide more detailed explanation",
                "Missing source citations",
                "Information seems outdated",
                "Didn't fully answer my question"
            ]
        }
        
        for i in range(num_feedback):
            rating = random.choice(["positive"] * 87 + ["negative"] * 13)  # 87% positive
            
            feedback = {
                "feedback_id": f"fb-{i:06d}",
                "conversation_id": f"conv-{random.randint(1000, 9999)}",
                "response_id": f"resp-{random.randint(10000, 99999)}",
                "timestamp": (datetime.now() - timedelta(days=random.randint(0, days))).isoformat(),
                "agent_id": self.agent_id,
                "rating": rating,
                "feedback_text": random.choice(feedback_templates[rating]) if random.random() > 0.3 else "",
                "user_id": f"user{random.randint(1, 50)}@company.com",
                "categories": []
            }
            
            # Add categories based on feedback text
            if "slow" in feedback["feedback_text"].lower():
                feedback["categories"].append("latency")
            if "detail" in feedback["feedback_text"].lower():
                feedback["categories"].append("completeness")
            if "citation" in feedback["feedback_text"].lower() or "source" in feedback["feedback_text"].lower():
                feedback["categories"].append("citations")
            if not feedback["categories"]:
                feedback["categories"].append("general")
            
            feedback_list.append(feedback)
        
        helpers.print_success(f"Collected {len(feedback_list)} feedback items")
        return feedback_list
    # </feedback_api>
    
    # <feedback_analysis>
    # NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    def analyze_feedback(self, feedback_list: List[Dict]) -> Dict:
        """
        Analyze collected feedback to extract insights.
        
        Performs:
        - Rating aggregation
        - Topic extraction
        - Trend analysis
        - Suggestion identification
        
        Args:
            feedback_list: List of feedback dictionaries
            
        Returns:
            Analysis results dictionary
        """
        helpers.print_info("Analyzing user feedback...")
        
        if not feedback_list:
            return {"error": "No feedback to analyze"}
        
        # Calculate rating statistics
        total = len(feedback_list)
        positive = sum(1 for f in feedback_list if f["rating"] == "positive")
        negative = total - positive
        
        # Extract and count suggestions from negative feedback
        suggestions = {}
        for feedback in feedback_list:
            if feedback["rating"] == "negative" and feedback["feedback_text"]:
                # Simple keyword-based categorization
                text = feedback["feedback_text"].lower()
                if "slow" in text or "faster" in text or "latency" in text:
                    suggestions["Faster response times"] = suggestions.get("Faster response times", 0) + 1
                elif "detail" in text or "explanation" in text or "more" in text:
                    suggestions["More detailed explanations"] = suggestions.get("More detailed explanations", 0) + 1
                elif "citation" in text or "source" in text:
                    suggestions["Better source citations"] = suggestions.get("Better source citations", 0) + 1
                elif "outdated" in text or "current" in text:
                    suggestions["More current information"] = suggestions.get("More current information", 0) + 1
                else:
                    suggestions["General improvement"] = suggestions.get("General improvement", 0) + 1
        
        # Sort suggestions by frequency
        top_suggestions = [
            {"text": text, "count": count, "percentage": (count / negative * 100) if negative > 0 else 0}
            for text, count in sorted(suggestions.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # Analyze trends over time (by week)
        weekly_trends = {}
        for feedback in feedback_list:
            week = datetime.fromisoformat(feedback["timestamp"]).strftime("%Y-W%U")
            if week not in weekly_trends:
                weekly_trends[week] = {"positive": 0, "negative": 0}
            weekly_trends[week][feedback["rating"]] += 1
        
        # Calculate satisfaction trend
        for week in weekly_trends:
            total_week = weekly_trends[week]["positive"] + weekly_trends[week]["negative"]
            weekly_trends[week]["satisfaction_rate"] = (
                weekly_trends[week]["positive"] / total_week if total_week > 0 else 0
            )
        
        # Analyze by category
        category_stats = {}
        for feedback in feedback_list:
            for category in feedback["categories"]:
                if category not in category_stats:
                    category_stats[category] = {"positive": 0, "negative": 0}
                category_stats[category][feedback["rating"]] += 1
        
        analysis = {
            "statistics": {
                "total_feedback": total,
                "positive_count": positive,
                "negative_count": negative,
                "satisfaction_rate": positive / total if total > 0 else 0,
                "feedback_with_text": sum(1 for f in feedback_list if f["feedback_text"])
            },
            "top_suggestions": top_suggestions[:10],
            "weekly_trends": weekly_trends,
            "category_stats": category_stats,
            "recommendations": self._generate_feedback_recommendations(
                positive / total if total > 0 else 0,
                top_suggestions
            )
        }
        
        return analysis
    # </feedback_analysis>
    
    def _generate_feedback_recommendations(
        self,
        satisfaction_rate: float,
        top_suggestions: List[Dict]
    ) -> List[str]:
        """Generate recommendations based on feedback analysis."""
        recommendations = []
        
        if satisfaction_rate < 0.80:
            recommendations.append(
                "Satisfaction rate below 80% - prioritize addressing top user concerns"
            )
        
        if top_suggestions:
            top_issue = top_suggestions[0]
            if top_issue["percentage"] > 20:
                recommendations.append(
                    f"Address primary concern: {top_issue['text']} ({top_issue['percentage']:.0f}% of negative feedback)"
                )
        
        # Check for specific patterns
        suggestion_texts = [s["text"].lower() for s in top_suggestions]
        if any("faster" in s or "slow" in s for s in suggestion_texts):
            recommendations.append(
                "Performance optimization recommended - users requesting faster responses"
            )
        
        if any("detail" in s or "explanation" in s for s in suggestion_texts):
            recommendations.append(
                "Enhance response completeness - consider providing more detailed explanations"
            )
        
        if any("citation" in s or "source" in s for s in suggestion_texts):
            recommendations.append(
                "Improve source attribution - users want better citations"
            )
        
        if not recommendations:
            recommendations.append(
                f"Maintain current quality - {satisfaction_rate*100:.1f}% satisfaction rate is excellent"
            )
        
        return recommendations
    
    def export_feedback_for_training(self, feedback_list: List[Dict], filename: str = "feedback_export.csv"):
        """Export feedback data for use in training datasets."""
        helpers.print_info("Exporting feedback for training data preparation...")
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                "feedback_id", "conversation_id", "response_id", "timestamp",
                "rating", "feedback_text", "user_id", "categories"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for feedback in feedback_list:
                row = feedback.copy()
                row["categories"] = ",".join(feedback["categories"])
                writer.writerow(row)
        
        helpers.print_success(f"Exported {len(feedback_list)} feedback items to {filename}")
    
    def run(self) -> Dict:
        """Execute complete feedback collection workflow."""
        helpers.print_header("Human Feedback Collection & Analysis")
        
        # Collect feedback
        feedback_list = self.collect_feedback_from_production(days=30)
        
        # Analyze feedback
        analysis = self.analyze_feedback(feedback_list)
        
        # Display results
        helpers.print_feedback_summary(analysis)
        
        # Export for training
        self.export_feedback_for_training(feedback_list)
        
        # Save results
        result = {
            "feedback_data": feedback_list,
            "analysis": analysis,
            "timestamp": helpers.format_timestamp()
        }
        
        helpers.save_json(
            {"statistics": analysis["statistics"], 
             "top_suggestions": analysis["top_suggestions"],
             "recommendations": analysis["recommendations"]},
            "feedback_summary.json"
        )
        
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
    
    collector = FeedbackCollection(project_client, agent_id)
    collector.run()

if __name__ == "__main__":
    main()
