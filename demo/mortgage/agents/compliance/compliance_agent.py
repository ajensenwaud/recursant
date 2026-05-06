"""Compliance Crew Agent — reviews mortgage applications for regulatory compliance using CrewAI.

Flask A2A server on port 5025. Runs a CrewAI crew with three agents:
  - Document Reviewer: checks application documents
  - Policy Checker: validates lending regulations
  - Risk Assessor: produces final compliance verdict

The crew executes sequentially: Doc Reviewer -> Policy Checker -> Risk Assessor.
"""

from __future__ import annotations

import json
import os
import uuid

from flask import Flask, jsonify, request

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

_tool_client = None


def get_tool_client():
    """Get tool client — sidecar or direct MCP depending on config."""
    global _tool_client
    if _tool_client is None:
        if os.environ.get("USE_SIDECAR_TOOLS", "0") == "1":
            from mcp_client import SidecarToolClient
            sidecar_url = os.environ.get(
                "SIDECAR_URL_COMPLIANCE",
                os.environ.get("SIDECAR_URL", "http://localhost:9915"),
            )
            _tool_client = SidecarToolClient(sidecar_url)
        else:
            from mcp_client import MCPToolClient
            _tool_client = MCPToolClient(
                server_script="/app/mcp_servers/compliance_engine.py",
                env={**os.environ, "STUB_API_URL": os.environ.get("STUB_API_URL", "http://stub-apis:6000")},
            )
    return _tool_client


# ---------------------------------------------------------------------------
# CrewAI tool bridges — @tool decorated functions that call through the
# tool client (sidecar or MCP) for governance and audit.
# ---------------------------------------------------------------------------

from crewai.tools import tool


@tool
def check_lending_regulations(loan_amount: float, property_value: float, annual_income: float) -> str:
    """Check mortgage lending regulations including LTV and DTI ratio compliance.
    Args:
        loan_amount: The mortgage loan amount requested
        property_value: The value of the property being purchased
        annual_income: The applicant's annual income
    """
    client = get_tool_client()
    return client.call_tool_sync("check_lending_regulations", {
        "loan_amount": loan_amount,
        "property_value": property_value,
        "annual_income": annual_income,
    })


@tool
def verify_document_completeness(document_types_provided: str) -> str:
    """Check that all required documents have been provided for the mortgage application.
    Args:
        document_types_provided: Comma-separated list of document types provided (e.g. 'passport,payslip')
    """
    client = get_tool_client()
    return client.call_tool_sync("verify_document_completeness", {
        "document_types_provided": document_types_provided,
    })


@tool
def calculate_compliance_score(findings: str) -> str:
    """Calculate a compliance score (0-100) based on review findings.
    Args:
        findings: A summary of all compliance findings from the review
    """
    client = get_tool_client()
    return client.call_tool_sync("calculate_compliance_score", {
        "findings": findings,
    })


# ---------------------------------------------------------------------------
# CrewAI crew builder
# ---------------------------------------------------------------------------

def build_crew(payload: dict):
    """Build a CrewAI crew for compliance review."""
    from crewai import Agent, Crew, Process, Task, LLM

    # CrewAI uses provider/model format. Moonshot and OpenRouter are
    # OpenAI-compatible via litellm.
    if LLM_PROVIDER == 'moonshot':
        os.environ.setdefault("OPENAI_API_BASE", "https://api.moonshot.ai/v1")
        os.environ.setdefault("OPENAI_API_KEY", os.environ.get("MOONSHOT_API_KEY", ""))
        llm = LLM(
            model=f"openai/{LLM_MODEL}",
            base_url="https://api.moonshot.ai/v1",
            api_key=os.environ.get("MOONSHOT_API_KEY", ""),
        )
    elif LLM_PROVIDER == 'openrouter':
        os.environ.setdefault("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
        os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
        llm = LLM(
            model=f"openai/{LLM_MODEL}",
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
    elif LLM_PROVIDER == 'openai':
        llm = f"openai/{LLM_MODEL}"
    else:
        llm = f"anthropic/{LLM_MODEL}"

    customer_name = payload.get("customer_name", "Unknown")
    loan_amount = payload.get("loan_amount", 0)
    property_value = payload.get("property_value", 0)
    annual_salary = payload.get("annual_salary", 0)
    docs_provided = payload.get("document_types_provided", "")

    # --- Agents ---
    doc_reviewer = Agent(
        role="Document Reviewer",
        goal="Verify that all required documents have been provided for the mortgage application",
        backstory="You are a meticulous document reviewer at a bank's compliance department. "
                  "You check that every required document is present before a mortgage can proceed.",
        tools=[verify_document_completeness],
        llm=llm,
        verbose=False,
    )

    policy_checker = Agent(
        role="Policy Checker",
        goal="Validate the mortgage application against lending regulations (LTV, DTI ratios)",
        backstory="You are a regulatory compliance officer who ensures all mortgage applications "
                  "meet government lending regulations and bank policies.",
        tools=[check_lending_regulations],
        llm=llm,
        verbose=False,
    )

    risk_assessor = Agent(
        role="Risk Assessor",
        goal="Produce a final compliance verdict and score based on all findings",
        backstory="You are a senior risk assessor who synthesises findings from document review "
                  "and policy checks to produce a final compliance verdict.",
        tools=[calculate_compliance_score],
        llm=llm,
        verbose=False,
    )

    # --- Tasks ---
    doc_review_task = Task(
        description=f"Check document completeness for {customer_name}'s mortgage application. "
                    f"Documents provided: {docs_provided}. "
                    f"Use the verify_document_completeness tool with the document_types_provided parameter.",
        expected_output="A summary of which documents are present and which are missing.",
        agent=doc_reviewer,
    )

    policy_check_task = Task(
        description=f"Check lending regulations for {customer_name}'s mortgage application. "
                    f"Loan amount: {loan_amount}, Property value: {property_value}, "
                    f"Annual income: {annual_salary}. "
                    f"Use the check_lending_regulations tool with loan_amount, property_value, and annual_income parameters.",
        expected_output="A summary of LTV ratio, DTI ratio, and any regulatory violations.",
        agent=policy_checker,
    )

    risk_assessment_task = Task(
        description="Based on the document review and policy check findings from the previous tasks, "
                    "produce a final compliance verdict. Summarise all findings into a single string and "
                    "use the calculate_compliance_score tool with the findings parameter. "
                    "Then produce the final output as JSON with keys: verdict (PASS or FAIL), "
                    "compliance_score (0-100), and findings (list of strings).",
        expected_output='JSON object: {"verdict": "PASS" or "FAIL", "compliance_score": 0-100, "findings": ["..."]}',
        agent=risk_assessor,
    )

    crew = Crew(
        agents=[doc_reviewer, policy_checker, risk_assessor],
        tasks=[doc_review_task, policy_check_task, risk_assessment_task],
        process=Process.sequential,
        verbose=False,
    )

    return crew


# ---------------------------------------------------------------------------
# A2A message handler
# ---------------------------------------------------------------------------

def handle_message(params: dict) -> dict:
    message_text = extract_text(params)
    if not message_text:
        return {"status": "failed", "artifacts": [{"kind": "text", "text": "No message"}]}

    try:
        payload = json.loads(message_text)
    except (json.JSONDecodeError, AttributeError):
        # Non-JSON input — return a generic response
        return {
            "status": "completed",
            "id": str(uuid.uuid4()),
            "artifacts": [{"kind": "text", "text": json.dumps({
                "verdict": "FAIL",
                "compliance_score": 0,
                "findings": ["Unable to parse compliance review request"],
            })}],
        }

    try:
        crew = build_crew(payload)
        result = crew.kickoff()
        result_text = str(result)

        # Try to extract JSON from the result
        try:
            # CrewAI might wrap the JSON in extra text, try to find it
            import re
            json_match = re.search(r'\{[^{}]*"verdict"[^{}]*\}', result_text)
            if json_match:
                parsed = json.loads(json_match.group())
                result_text = json.dumps(parsed)
            else:
                # If we can't find JSON, construct one from the raw output
                result_text = json.dumps({
                    "verdict": "PASS" if "pass" in result_text.lower() else "FAIL",
                    "compliance_score": 100 if "pass" in result_text.lower() else 50,
                    "findings": [result_text[:500]],
                })
        except (json.JSONDecodeError, AttributeError):
            result_text = json.dumps({
                "verdict": "PASS" if "pass" in result_text.lower() else "FAIL",
                "compliance_score": 100 if "pass" in result_text.lower() else 50,
                "findings": [result_text[:500]],
            })

    except Exception as e:
        print(f"CrewAI error: {e}")
        result_text = json.dumps({
            "verdict": "FAIL",
            "compliance_score": 0,
            "findings": [f"Compliance review error: {str(e)}"],
        })

    return {
        "status": "completed",
        "id": str(uuid.uuid4()),
        "artifacts": [{"kind": "text", "text": result_text}],
    }


def extract_text(params: dict) -> str | None:
    message = params.get("message", {})
    parts = message.get("parts", []) if isinstance(message, dict) else []
    for part in parts:
        if isinstance(part, dict) and part.get("kind") == "text":
            return part.get("text")
    return None


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

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

    if method == "message/send":
        result = handle_message(data.get("params", {}))
        return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})

    return jsonify({
        "jsonrpc": "2.0", "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }), 404


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "agent": "compliance-crew"})


if __name__ == "__main__":
    port = int(os.environ.get("COMPLIANCE_AGENT_PORT", "5025"))
    print(f"Compliance Crew Agent starting on port {port}")
    app.run(host="0.0.0.0", port=port)
