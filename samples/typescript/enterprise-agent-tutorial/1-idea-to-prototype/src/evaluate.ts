#!/usr/bin/env node
/**
 * Evaluation Script for Modern Workplace Assistant
 * Tests the agent with predefined business scenarios to assess quality.
 *
 * Updated for Azure AI Agents SDK v2.
 */

// <imports_and_includes>
import * as fs from "fs";
import * as path from "path";
import { chatWithAssistant } from "./main";
import { AgentsClient } from "@azure/ai-agents-ii";
import { DefaultAzureCredential } from "@azure/identity";
import { config } from "dotenv";
// </imports_and_includes>

config();

const credential = new DefaultAzureCredential();
const agentsClient = new AgentsClient(
  process.env.PROJECT_ENDPOINT || "",
  credential
);

interface Question {
  question: string;
  test_type: string;
  expected_source: string;
  validation: string;
  explanation: string;
}

interface EvaluationResult {
  question: string;
  response: string;
  status: string;
  passed: boolean;
  validation_details: string;
  test_type: string;
  expected_source: string;
  explanation: string;
}

interface Stats {
  passed: number;
  total: number;
}

// <load_test_data>
function loadTestQuestions(filepath: string = "questions.jsonl"): Question[] {
  /**
   * Load test questions from JSONL file
   */
  const questions: Question[] = [];
  const content = fs.readFileSync(filepath, "utf-8");
  const lines = content.split("\n").filter((line) => line.trim());

  for (const line of lines) {
    questions.push(JSON.parse(line));
  }

  return questions;
}
// </load_test_data>

// <validation_functions>
function validateResponse(
  response: string,
  validationType: string,
  expectedSource: string
): { passed: boolean; details: string } {
  /**
   * Validate that the response used the expected tools.
   *
   * Args:
   *   response: The agent's response text
   *   validationType: Type of validation to perform
   *   expectedSource: Expected data source (sharepoint, mcp, or both)
   *
   * Returns:
   *   Object with passed boolean and details string
   */
  const responseLower = response.toLowerCase();

  // Check for Contoso-specific content (indicates SharePoint usage)
  const contosoIndicators = [
    "contoso",
    "90-day probationary period",
    "2-hour incident reporting",
    "company policies",
    "our policy",
    "our remote work policy",
    "our security guidelines",
    "our collaboration standards",
    "our data governance",
  ];
  const hasContosoContent = contosoIndicators.some((indicator) =>
    responseLower.includes(indicator)
  );

  // Check for Microsoft Learn links (indicates MCP usage)
  const learnIndicators = [
    "learn.microsoft.com",
    "docs.microsoft.com",
    "microsoft learn",
    "official documentation",
    "reference link",
    "documentation link",
  ];
  const hasLearnLinks = learnIndicators.some((indicator) =>
    responseLower.includes(indicator)
  );

  // Validate based on expected source
  let passed: boolean;
  let details: string;

  if (expectedSource === "sharepoint") {
    passed = hasContosoContent;
    details = `Contoso-specific content: ${hasContosoContent}`;
  } else if (expectedSource === "mcp") {
    passed = hasLearnLinks;
    details = `Microsoft Learn links: ${hasLearnLinks}`;
  } else if (expectedSource === "both") {
    passed = hasContosoContent && hasLearnLinks;
    details = `Contoso content: ${hasContosoContent}, Learn links: ${hasLearnLinks}`;
  } else {
    passed = false;
    details = "Unknown validation type";
  }

  return { passed, details };
}
// </validation_functions>

// <run_batch_evaluation>
async function runEvaluation(agentId: string): Promise<EvaluationResult[]> {
  /**
   * Run evaluation with test questions using Agent SDK v2.
   *
   * Args:
   *   agentId: The ID of the agent to evaluate
   *
   * Returns:
   *   Array of evaluation results for each question
   */
  const questions = loadTestQuestions();
  const results: EvaluationResult[] = [];

  console.log(`🧪 Running evaluation with ${questions.length} test questions...`);
  console.log("=".repeat(70));

  // Track results by test type
  const stats: Record<string, Stats> = {
    sharepoint_only: { passed: 0, total: 0 },
    mcp_only: { passed: 0, total: 0 },
    hybrid: { passed: 0, total: 0 },
  };

  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const testType = q.test_type || "unknown";
    const expectedSource = q.expected_source || "unknown";
    const validationType = q.validation || "default";

    console.log(`\n📝 Question ${i + 1}/${questions.length} [${testType.toUpperCase()}]`);
    console.log(`   ${q.question.substring(0, 80)}...`);

    const { response, status } = await chatWithAssistant(agentId, q.question);

    // Validate response using source-specific checks
    const { passed, details } = validateResponse(
      response,
      validationType,
      expectedSource
    );

    const result: EvaluationResult = {
      question: q.question,
      response: response,
      status: status,
      passed: passed,
      validation_details: details,
      test_type: testType,
      expected_source: expectedSource,
      explanation: q.explanation || "",
    };
    results.push(result);

    // Update stats
    if (stats[testType]) {
      stats[testType].total += 1;
      if (passed) {
        stats[testType].passed += 1;
      }
    }

    const statusIcon = passed ? "✅" : "⚠️";
    console.log(`${statusIcon} Status: ${status} | Tool check: ${details}`);
  }

  console.log("\n" + "=".repeat(70));
  console.log("📊 EVALUATION SUMMARY BY TEST TYPE:");
  console.log("=".repeat(70));

  for (const [testType, data] of Object.entries(stats)) {
    if (data.total > 0) {
      const passRate = (data.passed / data.total) * 100;
      const icon = passRate >= 75 ? "✅" : passRate >= 50 ? "⚠️" : "❌";
      console.log(
        `${icon} ${testType.toUpperCase()}: ${data.passed}/${data.total} passed (${passRate.toFixed(1)}%)`
      );
    }
  }

  return results;
}
// </run_batch_evaluation>

// <evaluation_results>
function calculateAndSaveResults(results: EvaluationResult[]): void {
  /**
   * Calculate pass rate and save results
   */
  const passed = results.filter((r) => r.passed).length;
  const total = results.length;
  const passRate = total > 0 ? (passed / total) * 100 : 0;

  console.log(
    `\n📊 Overall Evaluation Results: ${passed}/${total} questions passed (${passRate.toFixed(1)}%)`
  );

  // Save results
  fs.writeFileSync(
    "evaluation_results.json",
    JSON.stringify(results, null, 2)
  );

  console.log("💾 Results saved to evaluation_results.json");

  // Print summary of failures
  const failures = results.filter((r) => !r.passed);
  if (failures.length > 0) {
    console.log(`\n⚠️  Failed Questions (${failures.length}):`);
    for (const r of failures) {
      console.log(`   - [${r.test_type}] ${r.question.substring(0, 60)}...`);
      console.log(`     Reason: ${r.validation_details}`);
    }
  }
}
// </evaluation_results>

async function createWorkplaceAssistant() {
  /**
   * Create agent - simplified version for evaluation
   */
  console.log("🤖 Creating Modern Workplace Assistant for evaluation...");

  const instructions = `You are a Modern Workplace Assistant specializing in Azure and Microsoft 365 guidance.
Provide comprehensive technical guidance with step-by-step implementation instructions.`;

  const agent = await agentsClient.createAgent(
    process.env.MODEL_DEPLOYMENT_NAME || "gpt-4o",
    {
      name: "Modern Workplace Assistant",
      instructions: instructions,
    }
  );

  console.log(`✅ Agent created: ${agent.id}`);
  return agent;
}

async function main(): Promise<void> {
  /**
   * Run evaluation on the workplace assistant using Agent SDK v2.
   */
  console.log("🧪 Modern Workplace Assistant - Evaluation (Agent SDK v2)");
  console.log("=".repeat(70));

  try {
    // Create agent using SDK v2
    const agent = await createWorkplaceAssistant();

    console.log(`\n✅ Agent created: ${agent.id}`);
    console.log(`   Model: ${agent.model}`);
    console.log(`   Name: ${agent.name}`);
    console.log("=".repeat(70));

    // Run evaluation
    const results = await runEvaluation(agent.id);

    // Calculate and save results
    calculateAndSaveResults(results);
  } catch (error: any) {
    console.log(`\n❌ Evaluation failed: ${error.message}`);
    console.log(`Stack trace: ${error.stack}`);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
