#!/usr/bin/env python3
"""
Simple MCP HTTP Server for testing Azure AI Agents MCP tool.

This implements the Streamable HTTP transport for MCP protocol.
Exposes a single "hello" tool that returns a greeting message.
"""

from flask import Flask, request, jsonify, Response
import json
import uuid

app = Flask(__name__)

# MCP Server Info
SERVER_INFO = {
    "name": "hello-world-mcp",
    "version": "1.0.0"
}

# Define our tools
TOOLS = [
    {
        "name": "hello",
        "description": "Say hello to someone. Returns a personalized greeting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the person to greet"
                }
            },
            "required": ["name"]
        }
    }
]


def handle_initialize(params):
    """Handle initialize request"""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {}
        },
        "serverInfo": SERVER_INFO
    }


def handle_tools_list(params):
    """Handle tools/list request"""
    return {
        "tools": TOOLS
    }


def handle_tools_call(params):
    """Handle tools/call request"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    if tool_name == "hello":
        name = arguments.get("name", "World")
        greeting = f"Hello, {name}! This is a response from the MCP server running in Azure Container Apps."
        return {
            "content": [
                {
                    "type": "text",
                    "text": greeting
                }
            ]
        }
    else:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Unknown tool: {tool_name}"
                }
            ],
            "isError": True
        }


@app.route("/", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "server": SERVER_INFO})


@app.route("/", methods=["POST"])
def mcp_handler():
    """Handle MCP JSON-RPC requests"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": "Parse error: invalid JSON"
                },
                "id": None
            }), 400
        
        method = data.get("method")
        params = data.get("params", {})
        request_id = data.get("id")
        
        print(f"MCP Request: method={method}, id={request_id}")
        
        # Handle different MCP methods
        if method == "initialize":
            result = handle_initialize(params)
        elif method == "notifications/initialized":
            # This is a notification, no response needed
            return "", 202
        elif method == "tools/list":
            result = handle_tools_list(params)
        elif method == "tools/call":
            result = handle_tools_call(params)
        else:
            return jsonify({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                },
                "id": request_id
            }), 200
        
        response = {
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        }
        
        print(f"MCP Response: {json.dumps(response)[:200]}")
        return jsonify(response)
        
    except Exception as e:
        print(f"MCP Error: {str(e)}")
        return jsonify({
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            },
            "id": data.get("id") if data else None
        }), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 80))
    print(f"Starting MCP HTTP Server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
