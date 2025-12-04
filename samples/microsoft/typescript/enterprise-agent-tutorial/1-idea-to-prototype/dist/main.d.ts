#!/usr/bin/env node
/**
 * Azure AI Foundry Agent Sample - Tutorial 1: Modern Workplace Assistant
 *
 * This sample demonstrates a complete business scenario using Azure AI Agents SDK v2:
 * - Agent creation with the new SDK
 * - Thread and message management
 * - Robust error handling and graceful degradation
 *
 * Educational Focus:
 * - Enterprise AI patterns with Agent SDK v2
 * - Real-world business scenarios that enterprises face daily
 * - Production-ready error handling and diagnostics
 * - Foundation for governance, evaluation, and monitoring (Tutorials 2-3)
 *
 * Business Scenario:
 * An employee needs to implement Azure AD multi-factor authentication. They need:
 * 1. Company security policy requirements
 * 2. Technical implementation steps
 * 3. Combined guidance showing how policy requirements map to technical implementation
 */
interface ChatResponse {
    response: string;
    status: string;
}
export declare function chatWithAssistant(agentId: string, message: string): Promise<ChatResponse>;
export {};
//# sourceMappingURL=main.d.ts.map