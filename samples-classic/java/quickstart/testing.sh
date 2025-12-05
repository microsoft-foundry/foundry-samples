#!/bin/bash
# Automated testing script for Azure AI Foundry Java Samples
# Usage: ./testing.sh [Optional SampleName]

set -e  # Exit on error

# Function to display colored output
print_color() {
    color_code=$1
    shift
    echo -e "\033[${color_code}m$@\033[0m"
}

# Function to check required environment variables
check_required_env() {
    missing_vars=()
    
    # Check for PROJECT_ENDPOINT (primary) or AZURE_ENDPOINT (fallback)
    if [ -z "$PROJECT_ENDPOINT" ]; then
        if [ -z "$AZURE_ENDPOINT" ]; then
            missing_vars+=("PROJECT_ENDPOINT or AZURE_ENDPOINT")
        else
            print_color "36" "Using AZURE_ENDPOINT as fallback for PROJECT_ENDPOINT"
        fi
    fi
    
    # Check for optional variables but provide information about defaults
    if [ -z "$AZURE_MODEL_DEPLOYMENT_NAME" ]; then
        print_color "36" "No AZURE_MODEL_DEPLOYMENT_NAME provided, using default: phi-4"
    fi
    
    if [ -z "$AZURE_MODEL_API_PATH" ]; then
        print_color "36" "No AZURE_MODEL_API_PATH provided, using default: deployments"
    fi
    
    # Check for authentication mechanism
    if [ ! -z "$AZURE_AI_API_KEY" ]; then
        print_color "36" "Authentication will use AZURE_AI_API_KEY"
    else
        print_color "36" "Authentication will use DefaultAzureCredential (requires az login)"
    fi
    
    # Add informational output about which SDKs will be tested
    print_color "36" "=============================================================="
    print_color "36" "   TESTING WITH AZURE AI SDKS"
    print_color "36" "=============================================================="
    print_color "36" "Azure AI Agents Persistent SDK v1.0.0-beta.2"
    print_color "36" "Azure AI Projects SDK v1.0.0-beta.2"
    print_color "36" "Azure AI Inference SDK v1.0.0-beta.5"
    print_color "36" "OpenAI Java SDK v2.7.0"
    print_color "36" "=============================================================="
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        print_color "31" "ERROR: Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            print_color "31" "  - $var"
        done
        print_color "31" "Please set these variables in your environment before running tests."
        return 1
    fi
    return 0
}

# Function to run a test and track its result
run_test() {
    sample=$1
    print_color "36" "\n=============================================================="
    print_color "36" "   RUNNING TEST: $sample"
    print_color "36" "==============================================================\n"
    
    # Run the test
    if mvn compile exec:java -Dexec.mainClass="com.azure.ai.foundry.samples.$sample"; then
        print_color "32" "\n✓ TEST PASSED: $sample"
        return 0
    else
        print_color "31" "\n✗ TEST FAILED: $sample"
        return 1
    fi
}

# Check for Java and Maven
if ! command -v java &> /dev/null; then
    print_color "31" "Error: Java is not installed or not in PATH"
    exit 1
fi

if ! command -v mvn &> /dev/null; then
    print_color "31" "Error: Maven is not installed or not in PATH"
    exit 1
fi

# Check if user is logged in with Azure CLI
print_color "36" "Checking Azure CLI login status..."
if ! az account show > /dev/null 2>&1; then
    print_color "31" "Error: You are not logged in with the Azure CLI. Please run 'az login' first."
    exit 1
else
    print_color "32" "Azure CLI login validated."
fi

# Check for required environment variables
print_color "36" "Validating environment variables..."
check_required_env || exit 1
print_color "32" "Environment variables validation passed."

# Build the project first
print_color "36" "\n=============================================================="
print_color "36" "   BUILDING PROJECT"
print_color "36" "==============================================================\n"

if ! mvn clean compile; then
    print_color "31" "Error: Failed to build the project"
    exit 1
fi

# Track overall success
success=true

# If a specific test is specified, run only that test
if [ "$1" != "" ]; then
    if run_test "$1"; then
        print_color "32" "\nSingle test completed successfully."
    else
        print_color "31" "\nSingle test failed."
        exit 1
    fi
    exit 0
fi

# Run all tests in sequence
samples=(
    "CreateProject"
    "ChatCompletionSample"
    "ChatCompletionStreamingSample"
    "AgentSample"
    "FileSearchAgentSample"
    "EvaluateAgentSample"
)

# Conditionally add OpenAI sample if API key is set
if [ ! -z "$OPENAI_API_KEY" ]; then
    samples+=("ChatCompletionOpenAISample")
else
    print_color "33" "\nSkipping ChatCompletionOpenAISample (OPENAI_API_KEY not set)"
fi

# Always add the inference sample, even though it may fail due to SDK limitations
samples+=("ChatCompletionInferenceSample")

# Arrays to track results
passed_tests=()
failed_tests=()

# Run each test
for sample in "${samples[@]}"; do
    if run_test "$sample"; then
        passed_tests+=("$sample")
    else
        failed_tests+=("$sample")
        success=false
    fi
    
    # Short pause between tests
    sleep 2
done

# Print summary
print_color "36" "\n=============================================================="
print_color "36" "   TEST SUMMARY"
print_color "36" "==============================================================\n"

print_color "32" "PASSED TESTS (${#passed_tests[@]}):"
for test in "${passed_tests[@]}"; do
    print_color "32" "  ✓ $test"
done

if [ ${#failed_tests[@]} -gt 0 ]; then
    print_color "31" "\nFAILED TESTS (${#failed_tests[@]}):"
    for test in "${failed_tests[@]}"; do
        print_color "31" "  ✗ $test"
    done
    print_color "31" "\nSome tests failed. Please check the logs above for details."
    exit 1
else
    print_color "32" "\nAll tests passed successfully!"
fi
print_color "36" "\n=============================================================="
print_color "36" "   TESTING COMPLETED"
print_color "36" "==============================================================\n"
# Exit with success status
if $success; then
    exit 0
else
    exit 1
fi
# End of testing script