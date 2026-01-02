# ModelGateway Troubleshooting Guide

This guide helps you diagnose and fix common issues when setting up ModelGateway connections for Azure AI Foundry Agents.

## 🔧 Quick Diagnosis

**Before troubleshooting, use the validation script from the [setup guide](./modelgateway-setup-guide-for-agents.md#-connection-validation) to test your configuration.**

This script will help identify the root cause of most issues.

---

## 🚨 Common Issues

### 1. 404/400 Resource Not Found or Deployment Not Found Errors

#### **Symptoms:**
- Agents return "404 Resource Not Found" errors
- "400 Bad Request - Deployment Not Found" errors
- Connection test fails with resource/deployment errors

#### **Root Cause:**
Generally caused by incorrectly configured gateway parameters in your ModelGateway connection.

#### **Critical Parameters to Check:**

| Parameter | Description |
|-----------|-------------|
| **`target`** | Base URL of your gateway endpoint |
| **`inferenceAPIVersion`** | API version for chat completions calls |
| **`deploymentInPath`** | Whether model name is in URL path vs request body |

#### **Solution:**
1. **Follow the [Setup Guide](./modelgateway-setup-guide-for-agents.md)** to verify your gateway configuration
2. **Run the validation script** to identify incorrect parameters (see [connection validation](./modelgateway-setup-guide-for-agents.md#-connection-validation) for instructions)
3. **Update your connection** with the correct parameters identified by the script
4. **Test again** to verify the fixes