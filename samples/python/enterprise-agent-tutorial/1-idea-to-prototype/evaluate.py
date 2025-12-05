#!/usr/bin/env python3
"""
Evaluation Script for Modern Workplace Assistant
Tests the agent with predefined business scenarios to assess quality.

Updated for Azure AI Agents SDK v2.
"""

# <imports_and_includes>
import json
from main import create_workplace_assistant, chat_with_assistant
# </imports_and_includes>

# <load_test_data>
# NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
def load_test_questions(filepath="questions.jsonl"):
    """Load test questions from JSONL file"""
    questions = []
    with open(filepath, 'r') as f:
        for line in f:
            questions.append(json.loads(line.strip()))
    return questions
# </load_test_data>

# <validation_functions>
def validate_response(response, validation_type, expected_source):
    """
    Validate that the response used the expected tools.
    
    Args:
        response: The agent's response text
        validation_type: Type of validation to perform
        expected_source: Expected data source (sharepoint, mcp, or both)
        
    Returns:
        tuple: (passed, details)
    """
    response_lower = response.lower()
    
    # Check for Contoso-specific content (indicates SharePoint usage)
    contoso_indicators = [
        "contoso",
        "90-day probationary period",  # Specific to remote work policy
        "2-hour incident reporting",    # Specific to security policy
        "company policies",
        "our policy",
        "our remote work policy",
        "our security guidelines",
        "our collaboration standards",
        "our data governance"
    ]
    has_contoso_content = any(indicator in response_lower for indicator in contoso_indicators)
    
    # Check for Microsoft Learn links (indicates MCP usage)
    learn_indicators = [
        "learn.microsoft.com",
        "docs.microsoft.com",
        "microsoft learn",
        "official documentation",
        "reference link",
        "documentation link"
    ]
    has_learn_links = any(indicator in response_lower for indicator in learn_indicators)
    
    # Validate based on expected source
    if expected_source == "sharepoint":
        passed = has_contoso_content
        details = f"Contoso-specific content: {has_contoso_content}"
    elif expected_source == "mcp":
        passed = has_learn_links
        details = f"Microsoft Learn links: {has_learn_links}"
    elif expected_source == "both":
        passed = has_contoso_content and has_learn_links
        details = f"Contoso content: {has_contoso_content}, Learn links: {has_learn_links}"
    else:
        passed = False
        details = "Unknown validation type"
    
    return passed, details
# </validation_functions>

# <run_batch_evaluation>
def run_evaluation(agent_id):
    """
    Run evaluation with test questions using Agent SDK v2.
    
    Args:
        agent_id: The ID of the agent to evaluate
        
    Returns:
        list: Evaluation results for each question
    """
    questions = load_test_questions()
    results = []
    
    print(f"🧪 Running evaluation with {len(questions)} test questions...")
    print("="*70)
    
    # Track results by test type
    stats = {
        "sharepoint_only": {"passed": 0, "total": 0},
        "mcp_only": {"passed": 0, "total": 0},
        "hybrid": {"passed": 0, "total": 0}
    }
    
    for i, q in enumerate(questions, 1):
        test_type = q.get("test_type", "unknown")
        expected_source = q.get("expected_source", "unknown")
        validation_type = q.get("validation", "default")
        
        print(f"\n📝 Question {i}/{len(questions)} [{test_type.upper()}]")
        print(f"   {q['question'][:80]}...")
        
        response, status = chat_with_assistant(agent_id, q["question"])
        
        # Validate response using source-specific checks
        passed, validation_details = validate_response(response, validation_type, expected_source)
        
        result = {
            "question": q["question"],
            "response": response,
            "status": status,
            "passed": passed,
            "validation_details": validation_details,
            "test_type": test_type,
            "expected_source": expected_source,
            "explanation": q.get("explanation", "")
        }
        results.append(result)
        
        # Update stats
        if test_type in stats:
            stats[test_type]["total"] += 1
            if passed:
                stats[test_type]["passed"] += 1
        
        status_icon = "✅" if passed else "⚠️"
        print(f"{status_icon} Status: {status} | Tool check: {validation_details}")
    
    print("\n" + "="*70)
    print("📊 EVALUATION SUMMARY BY TEST TYPE:")
    print("="*70)
    for test_type, data in stats.items():
        if data["total"] > 0:
            pass_rate = (data["passed"] / data["total"]) * 100
            icon = "✅" if pass_rate >= 75 else "⚠️" if pass_rate >= 50 else "❌"
            print(f"{icon} {test_type.upper()}: {data['passed']}/{data['total']} passed ({pass_rate:.1f}%)")
    
    return results
# </run_batch_evaluation>

# <evaluation_results>
def calculate_and_save_results(results):
    """Calculate pass rate and save results"""
    # Calculate pass rate
    passed = sum(1 for r in results if r.get("passed", False))
    total = len(results)
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"\n📊 Overall Evaluation Results: {passed}/{total} questions passed ({pass_rate:.1f}%)")
    
    # Save results
    with open("evaluation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"💾 Results saved to evaluation_results.json")
    
    # Print summary of failures
    failures = [r for r in results if not r.get("passed", False)]
    if failures:
        print(f"\n⚠️  Failed Questions ({len(failures)}):")
        for r in failures:
            print(f"   - [{r['test_type']}] {r['question'][:60]}...")
            print(f"     Reason: {r['validation_details']}")
# </evaluation_results>

def main():
    """
    Run evaluation on the workplace assistant using Agent SDK v2.
    """
    print("🧪 Modern Workplace Assistant - Evaluation (Agent SDK v2)")
    print("="*70)
    
    try:
        # Create agent using SDK v2
        agent = create_workplace_assistant()
        
        print(f"\n✅ Agent created: {agent.id}")
        print(f"   Model: {agent.model}")
        print(f"   Name: {agent.name}")
        print("="*70)
        
        # Run evaluation
        results = run_evaluation(agent.id)
        
        # Calculate and save results
        calculate_and_save_results(results)
        
    except Exception as e:
        import traceback
        print(f"\n❌ Evaluation failed: {e}")
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
