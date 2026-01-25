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
STARTUP_TIMEOUT = 30  # seconds
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
    main_py_path = sample_path / "main.py"
    requirements_path = sample_path / "requirements.txt"
    
    # Validate required files
    if not agent_yaml_path.exists():
        result["error"] = "agent.yaml not found"
        return result
    
    if not main_py_path.exists():
        result["error"] = "main.py not found"
        return result
    
    # Extract test input
    test_input = extract_test_input(agent_yaml_path)
    result["details"]["test_input"] = test_input[:100] + "..." if len(test_input) > 100 else test_input
    
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
    
    # Start the server
    print(f"Starting server for {sample_path.name}...")
    server_process = subprocess.Popen(
        [sys.executable, str(main_py_path)],
        cwd=str(sample_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # Wait for server to be ready
        print(f"Waiting for server to start (timeout: {STARTUP_TIMEOUT}s)...")
        if not wait_for_server(STARTUP_TIMEOUT):
            # Check if process died
            if server_process.poll() is not None:
                stdout, stderr = server_process.communicate()
                result["error"] = f"Server process exited unexpectedly. stderr: {stderr[:500]}"
            else:
                result["error"] = f"Server did not start within {STARTUP_TIMEOUT} seconds"
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
