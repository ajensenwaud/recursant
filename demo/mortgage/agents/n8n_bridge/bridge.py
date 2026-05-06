"""A2A-to-n8n webhook bridge.

Thin infrastructure translator (no LLM). Receives A2A JSON-RPC
messages and forwards them to n8n webhook endpoints, returning
the n8n response as an A2A artifact.

Runs on port 5022 (same as old KYC agent) for mesh compatibility.
"""

from __future__ import annotations

import json
import os
import uuid

import httpx
from flask import Flask, jsonify, request

N8N_WEBHOOK_BASE = os.environ.get("N8N_WEBHOOK_BASE", "http://localhost:5678")
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "5022"))

app = Flask(__name__)


@app.route("/a2a", methods=["POST"])
def a2a_handler():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "jsonrpc": "2.0", "id": None,
            "error": {"code": -32700, "message": "Parse error"},
        }), 400

    method = data.get("method")
    request_id = data.get("id")
    params = data.get("params", {})

    if method == "message/send":
        result = handle_message(params)
        return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})

    return jsonify({
        "jsonrpc": "2.0", "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }), 404


def handle_message(params: dict) -> dict:
    """Extract A2A message parts and forward to n8n webhook."""
    message = params.get("message", {})
    parts = message.get("parts", []) if isinstance(message, dict) else []

    text_content = ""
    image_data = None
    media_type = None

    for part in parts:
        if not isinstance(part, dict):
            continue
        kind = part.get("kind", "")
        if kind == "text":
            text_content = part.get("text", "")
        elif kind == "file":
            file_info = part.get("file", {})
            image_data = file_info.get("bytes")  # base64-encoded
            media_type = file_info.get("mimeType", "image/jpeg")

    if not text_content and not image_data:
        return {
            "status": "failed",
            "artifacts": [{"kind": "text", "text": "No message content"}],
        }

    # Build payload for n8n webhook
    webhook_payload = {}
    try:
        webhook_payload = json.loads(text_content)
    except (json.JSONDecodeError, TypeError):
        webhook_payload["message"] = text_content

    if image_data:
        webhook_payload["passport_image"] = image_data
        webhook_payload["media_type"] = media_type

    # Forward to n8n webhook
    webhook_url = f"{N8N_WEBHOOK_BASE}/webhook/kyc-verification"
    try:
        # Strip passport_image from log to avoid flooding
        log_payload = {k: v for k, v in webhook_payload.items() if k != "passport_image"}
        print(f"Forwarding to n8n: {webhook_url} payload_keys={list(webhook_payload.keys())}", flush=True)
        resp = httpx.post(webhook_url, json=webhook_payload, timeout=120.0)
        print(f"n8n response: status={resp.status_code} length={len(resp.text)} body={resp.text[:500]}", flush=True)
        resp.raise_for_status()
        result_text = resp.text
    except Exception as e:
        print(f"n8n webhook error: {e}", flush=True)
        result_text = json.dumps({"status": "error", "message": str(e)})

    return {
        "status": "completed",
        "id": str(uuid.uuid4()),
        "artifacts": [{"kind": "text", "text": result_text}],
    }


@app.route("/health", methods=["GET"])
def health():
    """Health check — also verifies n8n is reachable."""
    n8n_ok = False
    try:
        resp = httpx.get(f"{N8N_WEBHOOK_BASE}/healthz", timeout=5.0)
        n8n_ok = resp.status_code == 200
    except Exception:
        pass

    return jsonify({
        "status": "ok" if n8n_ok else "degraded",
        "agent": "n8n-kyc-bridge",
        "n8n_reachable": n8n_ok,
    })


if __name__ == "__main__":
    print(f"n8n A2A Bridge starting on port {BRIDGE_PORT}")
    app.run(host="0.0.0.0", port=BRIDGE_PORT)
