#!/usr/bin/env python3
"""
Test a hosted agent sample by starting the server and sending a test request.

Usage:
    python test_hosted_sample.py <sample_path>

The script will:
1. Install dependencies from requirements.txt
2. Start the server (python main.py)
3. Wait for server to be ready (up to 30 seconds)
4. Send a test request to /responses endpoint
5. Validate the response
6. Report success/failure with details
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml


DEFAULT_TEST_INPUT = "Hello, please introduce yourself briefly."
SERVER_PORT = 8088
SERVER_URL = f"http://localhost:{SERVER_PORT}"
STARTUP_TIMEOUT = 30  # seconds for Python
DOTNET_STARTUP_TIMEOUT = 60  # seconds for C# (longer due to JIT)
DOTNET_BUILD_TIMEOUT = 300  # 5 minutes for NuGet restore + compile
REQUEST_TIMEOUT = 120  # seconds


def extract_test_input(agent_yaml_path: Path) -> str:
    """Extract test input from agent.yaml metadata.example if available."""
    try:
        with open(agent_yaml_path) as f:
            config = yaml.safe_load(f)

        examples = config.get("metadata", {}).get("example", [])
        if examples and isinstance(examples, list):
            for example in examples:
                if example.get("role") == "user" and example.get("content"):
                    return example["content"]
    except Exception as e:
        print(f"Warning: Could not parse agent.yaml for test input: {e}")

    return DEFAULT_TEST_INPUT


def detect_language(sample_path: Path) -> str:
    """Detect the language/framework of a sample based on marker files."""
    if (sample_path / "main.py").exists() and (sample_path / "requirements.txt").exists():
        return "python"

    csproj_files = list(sample_path.glob("*.csproj"))
    if csproj_files and (sample_path / "Program.cs").exists():
        return "csharp"

    return "unknown"


def find_csproj(sample_path: Path) -> Path | None:
    """Find the .csproj file in the sample directory."""
    csproj_files = list(sample_path.glob("*.csproj"))
    return csproj_files[0] if csproj_files else None


def build_csharp_sample(sample_path: Path, csproj_path: Path) -> tuple[bool, str]:
    """Build a C# sample using dotnet build.

    Returns:
        Tuple of (success, error_message)
    """
    print(f"Building C# project {csproj_path.name}...")
    try:
        result = subprocess.run(
            ["dotnet", "build", str(csproj_path), "-c", "Release"],
            cwd=str(sample_path),
            capture_output=True,
            text=True,
            timeout=DOTNET_BUILD_TIMEOUT
        )
        if result.returncode != 0:
            # dotnet outputs compilation errors to stdout, not stderr
            error_output = result.stdout + result.stderr
            return False, f"Build failed:\n{error_output}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"Build timed out after {DOTNET_BUILD_TIMEOUT} seconds"
    except FileNotFoundError:
        return False, "dotnet CLI not found. Ensure .NET SDK is installed."


def start_csharp_server(sample_path: Path, csproj_path: Path) -> subprocess.Popen:
    """Start a C# sample server using dotnet run."""
    return subprocess.Popen(
        ["dotnet", "run", "--project", str(csproj_path), "-c", "Release", "--no-build"],
        cwd=str(sample_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def wait_for_server(timeout: int = STARTUP_TIMEOUT) -> bool:
    """Wait for the server to be ready to accept connections."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # Try to connect to the server
            response = requests.get(SERVER_URL, timeout=2)
            # Any response (even 404) means server is up
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(1)
        except requests.exceptions.Timeout:
            time.sleep(1)
    
    return False


def send_test_request(test_input: str) -> dict:
    """Send a test request to the /responses endpoint."""
    payload = {
        "input": test_input,
        "stream": False
    }
    
    response = requests.post(
        f"{SERVER_URL}/responses",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=REQUEST_TIMEOUT
    )
    
    return {
        "status_code": response.status_code,
        "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
        "success": response.status_code == 200
    }


def run_test(sample_path: Path) -> dict:
    """Run the full test for a sample."""
    result = {
        "sample": str(sample_path),
        "name": sample_path.name,
        "success": False,
        "error": None,
        "details": {}
    }

    agent_yaml_path = sample_path / "agent.yaml"

    # Validate agent.yaml exists
    if not agent_yaml_path.exists():
        result["error"] = "agent.yaml not found"
        return result

    # Detect language
    language = detect_language(sample_path)
    result["details"]["language"] = language

    if language == "unknown":
        result["error"] = "Could not detect sample language (no main.py or *.csproj found)"
        return result

    # Extract test input
    test_input = extract_test_input(agent_yaml_path)
    result["details"]["test_input"] = test_input[:100] + "..." if len(test_input) > 100 else test_input

    # Language-specific setup and server start
    if language == "python":
        main_py_path = sample_path / "main.py"
        requirements_path = sample_path / "requirements.txt"

        if not main_py_path.exists():
            result["error"] = "main.py not found"
            return result

        # Install dependencies
        print(f"Installing dependencies from {requirements_path}...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements_path), "-q"],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            result["error"] = f"Failed to install dependencies: {e.stderr}"
            return result

        # Start server
        print(f"Starting Python server for {sample_path.name}...")
        server_process = subprocess.Popen(
            [sys.executable, str(main_py_path)],
            cwd=str(sample_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        startup_timeout = STARTUP_TIMEOUT

    elif language == "csharp":
        csproj_path = find_csproj(sample_path)
        if not csproj_path:
            result["error"] = "No .csproj file found"
            return result

        # Build the project
        build_success, build_error = build_csharp_sample(sample_path, csproj_path)
        if not build_success:
            result["error"] = build_error
            return result

        result["details"]["build"] = "success"

        # Start server
        print(f"Starting C# server for {sample_path.name}...")
        server_process = start_csharp_server(sample_path, csproj_path)
        startup_timeout = DOTNET_STARTUP_TIMEOUT

    try:
        # Wait for server to be ready
        print(f"Waiting for server to start (timeout: {startup_timeout}s)...")
        if not wait_for_server(startup_timeout):
            # Check if process died
            if server_process.poll() is not None:
                stdout, stderr = server_process.communicate()
                result["error"] = f"Server process exited unexpectedly. stderr: {stderr[:500]}"
            else:
                result["error"] = f"Server did not start within {startup_timeout} seconds"
            return result
        
        result["details"]["server_started"] = True
        print("Server is ready. Sending test request...")
        
        # Send test request
        try:
            response = send_test_request(test_input)
            result["details"]["response_status"] = response["status_code"]
            
            if response["success"]:
                result["success"] = True
                # Extract output text if available
                body = response["body"]
                if isinstance(body, dict):
                    output_text = body.get("output_text", body.get("output", str(body)))
                    result["details"]["response_preview"] = str(output_text)[:200]
                print(f"✅ Test passed! Status: {response['status_code']}")
            else:
                result["error"] = f"Request failed with status {response['status_code']}: {response['body']}"
                print(f"❌ Test failed! Status: {response['status_code']}")
                
        except requests.exceptions.Timeout:
            result["error"] = f"Request timed out after {REQUEST_TIMEOUT} seconds"
        except requests.exceptions.RequestException as e:
            result["error"] = f"Request failed: {str(e)}"
            
    finally:
        # Clean up server process
        print("Shutting down server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
            server_process.wait()
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Test a hosted agent sample")
    parser.add_argument("sample_path", help="Path to the sample directory")
    parser.add_argument("--output", "-o", help="Output file for JSON result")
    args = parser.parse_args()
    
    sample_path = Path(args.sample_path)
    if not sample_path.is_absolute():
        sample_path = Path.cwd() / sample_path
    
    if not sample_path.exists():
        print(f"Error: Sample path not found: {sample_path}")
        sys.exit(1)
    
    print(f"=" * 60)
    print(f"Testing sample: {sample_path.name}")
    print(f"Path: {sample_path}")
    print(f"=" * 60)
    
    result = run_test(sample_path)
    
    # Output result
    result_json = json.dumps(result, indent=2)
    print(f"\nResult:\n{result_json}")
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(result_json)
    
    # Exit with appropriate code
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
