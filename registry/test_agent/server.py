"""
Flask server exposing A2A-compatible endpoint for the LangGraph agent.
"""

import logging
from flask import Flask, request, jsonify

from config import Config
from agent import invoke_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "type": "langgraph",
        "provider": Config.LLM_PROVIDER,
        "model": Config.LLM_MODEL
    })


@app.route('/invoke', methods=['POST'])
def invoke():
    """
    A2A-compatible invocation endpoint.

    Accepts:
        - {"message": "..."} - Standard A2A format
        - {"input": "..."} - Alternative format

    Returns:
        {"response": "...", "metadata": {...}}
    """
    data = request.json or {}

    # Extract input from various possible formats
    input_message = None

    # A2A JSON-RPC format: {"jsonrpc": "2.0", "method": "message/send", "params": {"message": {...}}}
    if data.get('jsonrpc') and data.get('params'):
        msg = data['params'].get('message', {})
        if isinstance(msg, dict):
            parts = msg.get('parts', [])
            texts = [p.get('text', '') for p in parts if isinstance(p, dict) and p.get('text')]
            if texts:
                input_message = ' '.join(texts)

    # Simple format fallback
    if not input_message:
        input_message = (
            data.get('message') or
            data.get('input') or
            data.get('query') or
            data.get('text')
        )

    if not input_message:
        return jsonify({
            "error": "No input provided",
            "details": "Request must include 'message' or 'input' field"
        }), 400

    logger.info(f"Received request: {input_message[:100]}...")

    try:
        response = invoke_agent(input_message)

        logger.info(f"Agent response: {response[:100]}...")

        return jsonify({
            "response": response,
            "output": response,  # Alternative key for compatibility
            "metadata": {
                "agent_type": "langgraph",
                "provider": Config.LLM_PROVIDER,
                "model": Config.LLM_MODEL
            }
        })

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "response": f"An error occurred: {str(e)}"
        }), 500


@app.route('/tools', methods=['GET'])
def list_tools():
    """List available tools."""
    from tools import AVAILABLE_TOOLS

    tools = []
    for name, info in AVAILABLE_TOOLS.items():
        tools.append({
            "name": name,
            "description": info["description"],
            "parameters": info["parameters"]
        })

    return jsonify({"tools": tools})


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with API information."""
    return jsonify({
        "name": "Recursant Test Agent",
        "type": "langgraph",
        "version": "1.0.0",
        "endpoints": {
            "/health": "Health check",
            "/invoke": "Invoke the agent (POST)",
            "/tools": "List available tools"
        }
    })


if __name__ == '__main__':
    logger.info(f"Starting Test Agent with {Config.LLM_PROVIDER}/{Config.LLM_MODEL}")
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )
