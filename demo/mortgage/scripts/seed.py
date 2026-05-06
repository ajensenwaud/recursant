"""Seed mortgage demo agents and hub-and-spoke mesh policies.

Creates 5 agents (Customer, Auth, KYC, Credit, Core Banking) in DRAFT
status and configures mesh policies so only the Customer Agent can
communicate with backend agents (hub-and-spoke topology).

Usage:
    python scripts/seed.py [--registry-url URL]

Environment variables:
    REGISTRY_URL: Registry base URL (default: http://localhost:5000)
    REGISTRY_USERNAME / REGISTRY_PASSWORD: Admin credentials
    MESH_API_KEY: API key for mesh endpoints
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

DEFAULT_REGISTRY_URL = "http://localhost:5000"


def login(base_url: str, username: str, password: str) -> str:
    resp = httpx.post(
        f"{base_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=10.0,
    )
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()["token"]


def get_auth_headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "default",
    }


def get_mesh_headers(mesh_api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "X-Mesh-API-Key": mesh_api_key,
    }


def cleanup_existing_agents(base_url: str, headers: dict) -> None:
    """Delete ALL existing agents to start with a clean slate."""
    resp = httpx.get(f"{base_url}/v1/agents", headers=headers, timeout=10.0)
    if resp.status_code != 200:
        return

    for agent in resp.json().get("agents", []):
        del_resp = httpx.delete(
            f"{base_url}/v1/agents/{agent['id']}",
            headers=headers,
            timeout=10.0,
        )
        print(f"  Deleted agent: {agent['name']} ({del_resp.status_code})")


def create_agent(base_url: str, headers: dict, agent_data: dict) -> dict:
    resp = httpx.post(
        f"{base_url}/v1/agents",
        json=agent_data,
        headers=headers,
        timeout=10.0,
    )
    if resp.status_code == 201:
        agent = resp.json()
        print(f"  Created agent: {agent['name']} (id={agent['id']})")
        return agent
    elif resp.status_code == 409:
        print(f"  Agent '{agent_data['name']}' already exists, finding...")
        list_resp = httpx.get(f"{base_url}/v1/agents", headers=headers, timeout=10.0)
        for a in list_resp.json().get("agents", []):
            if a["name"] == agent_data["name"]:
                print(f"  Found existing: {a['name']} (id={a['id']})")
                return a
    else:
        print(f"  ERROR creating agent: {resp.status_code} {resp.text}")
    return {}


def cleanup_existing_policies(base_url: str, mesh_headers: dict) -> None:
    """Delete ALL existing mesh policies to start with a clean slate."""
    resp = httpx.get(
        f"{base_url}/v1/mesh/policies", headers=mesh_headers, timeout=10.0,
    )
    if resp.status_code != 200:
        return

    for policy in resp.json().get("policies", []):
        del_resp = httpx.delete(
            f"{base_url}/v1/mesh/policies/{policy['id']}",
            headers=mesh_headers,
            timeout=10.0,
        )
        src = policy.get("source", policy.get("source_agent_name", "?"))
        dst = policy.get("destination", policy.get("dest_agent_name", "?"))
        print(f"  Deleted policy: {src} -> {dst} ({del_resp.status_code})")


def create_mesh_policy(base_url: str, headers: dict, policy: dict) -> None:
    resp = httpx.post(
        f"{base_url}/v1/mesh/policies",
        json=policy,
        headers=headers,
        timeout=10.0,
    )
    if resp.status_code == 201:
        print(f"  Policy: {policy['source_agent_name']} -> {policy['dest_agent_name']}: {policy['action']}")
    else:
        print(f"  Policy: {resp.status_code} {resp.text}")


def main():
    parser = argparse.ArgumentParser(description="Seed mortgage demo agents")
    parser.add_argument("--registry-url", default=os.environ.get("REGISTRY_URL", DEFAULT_REGISTRY_URL))
    parser.add_argument("--username", default=os.environ.get("REGISTRY_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("REGISTRY_PASSWORD", "admin"))
    parser.add_argument("--mesh-api-key", default=os.environ.get("MESH_API_KEY", "mesh-dev-key"))
    args = parser.parse_args()

    base_url = args.registry_url.rstrip("/")
    print(f"Seeding mortgage demo agents at {base_url}")

    # Login
    print("Logging in...")
    token = login(base_url, args.username, args.password)
    headers = get_auth_headers(token)
    mesh_headers = get_mesh_headers(args.mesh_api_key)

    # Cleanup — wipe ALL agents and policies for a clean slate
    print("\n--- Cleaning up existing agents ---")
    cleanup_existing_agents(base_url, headers)
    print("\n--- Cleaning up existing mesh policies ---")
    cleanup_existing_policies(base_url, mesh_headers)

    # Common agent fields
    common = {
        "owner_id": "mortgage-demo",
        "team_id": "mortgage-demo",
        "contact_email": "demo@agenticbank.example.com",
        "classification": "internal",
        "data_sensitivity": "pii",
        "risk_tier": "low",
    }

    # ---------------------------------------------------------------
    # Create 5 agents
    # ---------------------------------------------------------------
    print("\n--- Creating Agents ---")

    customer = create_agent(base_url, headers, {
        **common,
        "name": "Customer Agent",
        "description": "Guides customers through the mortgage origination process",
        "version": "1.0.0",
        "capabilities": [{
            "name": "mortgage-origination",
            "description": "Guides customers through a complete mortgage application",
        }],
        "endpoint": {
            "type": "langgraph",
            "url": "http://agents-customer:5020/a2a",
            "auth_method": "mtls",
        },
    })

    auth = create_agent(base_url, headers, {
        **common,
        "name": "Authentication Agent",
        "description": "Verifies customer BAN and PIN against Customer Master",
        "version": "1.0.0",
        "capabilities": [{
            "name": "authenticate-customer",
            "description": "Verifies a customer's BAN and PIN",
        }],
        "endpoint": {
            "type": "langgraph",
            "url": "http://agents-customer:5021/a2a",
            "auth_method": "mtls",
        },
    })

    kyc = create_agent(base_url, headers, {
        **common,
        "name": "KYC Agent",
        "description": "Performs Know Your Customer identity verification",
        "version": "1.0.0",
        "capabilities": [{
            "name": "kyc-verify",
            "description": "Verifies identity documents against KYC system",
        }],
        "endpoint": {
            "type": "langgraph",
            "url": "http://agents-kyc-credit:5022/a2a",
            "auth_method": "mtls",
        },
    })

    credit = create_agent(base_url, headers, {
        **common,
        "name": "Credit Agent",
        "description": "Assesses credit capacity and makes lending decisions",
        "version": "1.0.0",
        "capabilities": [
            {
                "name": "assess-credit-capacity",
                "description": "Calculates maximum mortgage loan from annual salary",
            },
            {
                "name": "make-credit-decision",
                "description": "Makes lending decision based on LTV ratio",
            },
        ],
        "endpoint": {
            "type": "langgraph",
            "url": "http://agents-kyc-credit:5023/a2a",
            "auth_method": "mtls",
        },
    })

    core_banking = create_agent(base_url, headers, {
        **common,
        "name": "Core Banking Agent",
        "description": "Handles mortgage loan disbursement",
        "version": "1.0.0",
        "capabilities": [{
            "name": "disburse-loan",
            "description": "Disburses approved mortgage loans",
        }],
        "endpoint": {
            "type": "langgraph",
            "url": "http://agents-core-banking:5024/a2a",
            "auth_method": "mtls",
        },
    })

    compliance = create_agent(base_url, headers, {
        **common,
        "name": "Compliance Crew",
        "description": "Reviews mortgage applications for regulatory compliance using CrewAI",
        "version": "1.0.0",
        "capabilities": [{
            "name": "compliance-review",
            "description": "Reviews a mortgage application for regulatory compliance",
        }],
        "endpoint": {
            "type": "crewai",
            "url": "http://agents-compliance:5025/a2a",
            "auth_method": "mtls",
        },
    })

    # ---------------------------------------------------------------
    # Create hub-and-spoke mesh policies
    # ---------------------------------------------------------------
    print("\n--- Mesh Policies (hub-and-spoke) ---")

    backend_agents = [
        ("Authentication Agent", "Auth"),
        ("KYC Agent", "KYC"),
        ("Credit Agent", "Credit"),
        ("Core Banking Agent", "Core Banking"),
        ("Compliance Crew", "Compliance"),
    ]

    priority = 0
    for agent_name, short_name in backend_agents:
        # Customer Agent -> Backend Agent
        create_mesh_policy(base_url, mesh_headers, {
            "source_agent_name": "Customer Agent",
            "dest_agent_name": agent_name,
            "action": "allow",
            "priority": priority,
        })
        priority += 1

        # Backend Agent -> Customer Agent (responses)
        create_mesh_policy(base_url, mesh_headers, {
            "source_agent_name": agent_name,
            "dest_agent_name": "Customer Agent",
            "action": "allow",
            "priority": priority,
        })
        priority += 1

    # Default deny
    create_mesh_policy(base_url, mesh_headers, {
        "source_agent_name": "*",
        "dest_agent_name": "*",
        "action": "deny",
        "priority": 100,
    })

    # ---------------------------------------------------------------
    # Register tools, approve, and assign to agents
    # ---------------------------------------------------------------
    print("\n--- Tool Governance ---")

    stub_api_base = "http://stub-apis:6000/api"

    tool_definitions = [
        {
            "name": "verify_customer",
            "description": "Verify customer BAN and PIN against Customer Master",
            "endpoint_url": f"{stub_api_base}/customer-master/verify",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-customer-master:8080/sse",
            "mcp_server_name": "Customer Master",
            "mcp_server_description": "MCP server for Customer Master system — verifies customer credentials",
            "backend_services": [{"url": f"{stub_api_base}/customer-master/verify", "method": "POST", "description": "Customer Master verification API"}],
        },
        {
            "name": "verify_identity",
            "description": "Verify identity documents against KYC system",
            "endpoint_url": f"{stub_api_base}/kyc/verify",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-kyc-system:8081/sse",
            "mcp_server_name": "KYC System",
            "mcp_server_description": "MCP server for KYC system — verifies identity documents",
            "backend_services": [{"url": f"{stub_api_base}/kyc/verify", "method": "POST", "description": "KYC identity verification API"}],
        },
        {
            "name": "assess_credit_capacity",
            "description": "Calculate maximum mortgage loan from annual salary",
            "endpoint_url": f"{stub_api_base}/credit/assess",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-credit-engine:8082/sse",
            "mcp_server_name": "Credit Engine",
            "mcp_server_description": "MCP server for Credit Engine — assesses credit capacity and makes lending decisions",
            "backend_services": [{"url": f"{stub_api_base}/credit/assess", "method": "POST", "description": "Credit capacity assessment API"}],
        },
        {
            "name": "make_credit_decision",
            "description": "Make lending decision based on LTV ratio",
            "endpoint_url": f"{stub_api_base}/credit/decide",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-credit-engine:8082/sse",
            "mcp_server_name": "Credit Engine",
            "mcp_server_description": "MCP server for Credit Engine — assesses credit capacity and makes lending decisions",
            "backend_services": [{"url": f"{stub_api_base}/credit/decide", "method": "POST", "description": "Credit decision API"}],
        },
        {
            "name": "disburse_loan",
            "description": "Disburse approved mortgage loan",
            "endpoint_url": f"{stub_api_base}/core-banking/disburse",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-core-banking:8083/sse",
            "mcp_server_name": "Core Banking",
            "mcp_server_description": "MCP server for Core Banking system — handles loan disbursement",
            "backend_services": [{"url": f"{stub_api_base}/core-banking/disburse", "method": "POST", "description": "Loan disbursement API"}],
        },
        {
            "name": "check_lending_regulations",
            "description": "Check mortgage lending regulations including LTV and DTI ratio compliance",
            "endpoint_url": f"{stub_api_base}/compliance/check-regulations",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-compliance-engine:8084/sse",
            "mcp_server_name": "Compliance Engine",
            "mcp_server_description": "MCP server for Compliance Engine — regulatory checks for mortgage applications",
            "backend_services": [{"url": f"{stub_api_base}/compliance/check-regulations", "method": "POST", "description": "Lending regulations check API"}],
        },
        {
            "name": "verify_document_completeness",
            "description": "Check that all required documents have been provided for the mortgage application",
            "endpoint_url": f"{stub_api_base}/compliance/verify-documents",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-compliance-engine:8084/sse",
            "mcp_server_name": "Compliance Engine",
            "mcp_server_description": "MCP server for Compliance Engine — regulatory checks for mortgage applications",
            "backend_services": [{"url": f"{stub_api_base}/compliance/verify-documents", "method": "POST", "description": "Document completeness check API"}],
        },
        {
            "name": "calculate_compliance_score",
            "description": "Calculate a compliance score based on review findings",
            "endpoint_url": f"{stub_api_base}/compliance/calculate-score",
            "http_method": "POST",
            "mcp_server_url": "http://mcp-compliance-engine:8084/sse",
            "mcp_server_name": "Compliance Engine",
            "mcp_server_description": "MCP server for Compliance Engine — regulatory checks for mortgage applications",
            "backend_services": [{"url": f"{stub_api_base}/compliance/calculate-score", "method": "POST", "description": "Compliance score calculation API"}],
        },
    ]

    tool_ids = {}
    for tool_def in tool_definitions:
        tool_resp = httpx.post(
            f"{base_url}/v1/mesh/tools",
            json=tool_def,
            headers=headers,
            timeout=10.0,
        )
        if tool_resp.status_code == 201:
            tool_data = tool_resp.json()
            tool_ids[tool_def["name"]] = tool_data["id"]
            print(f"  Created tool: {tool_def['name']} (id={tool_data['id']})")
        elif tool_resp.status_code == 409:
            print(f"  Tool '{tool_def['name']}' already exists")
        else:
            print(f"  ERROR creating tool: {tool_resp.status_code} {tool_resp.text}")

    # Approve all tools
    for tool_name, tool_id in tool_ids.items():
        approve_resp = httpx.post(
            f"{base_url}/v1/mesh/tools/{tool_id}/approve",
            headers=headers,
            timeout=10.0,
        )
        if approve_resp.status_code == 200:
            print(f"  Approved tool: {tool_name}")
        else:
            print(f"  Approve {tool_name}: {approve_resp.status_code} {approve_resp.text}")

    # Assign tools to agents
    tool_assignments = {
        "verify_customer": "Authentication Agent",
        "verify_identity": "KYC Agent",
        "assess_credit_capacity": "Credit Agent",
        "make_credit_decision": "Credit Agent",
        "disburse_loan": "Core Banking Agent",
        "check_lending_regulations": "Compliance Crew",
        "verify_document_completeness": "Compliance Crew",
        "calculate_compliance_score": "Compliance Crew",
    }

    for tool_name, agent_name_assigned in tool_assignments.items():
        if tool_name not in tool_ids:
            continue
        assign_resp = httpx.post(
            f"{base_url}/v1/mesh/tool-assignments",
            json={"tool_id": tool_ids[tool_name], "agent_name": agent_name_assigned},
            headers=headers,
            timeout=10.0,
        )
        if assign_resp.status_code == 201:
            print(f"  Assigned {tool_name} -> {agent_name_assigned}")
        else:
            print(f"  Assign {tool_name}: {assign_resp.status_code} {assign_resp.text}")

    # ---------------------------------------------------------------
    # Create egress rules
    # ---------------------------------------------------------------
    print("\n--- Egress Rules ---")

    egress_rules = [
        {"agent_name": "*", "url_pattern": "http://stub-apis:6000/*", "action": "allow", "priority": 0},
        {"agent_name": "*", "url_pattern": "*", "action": "deny", "priority": 100},
    ]

    for rule in egress_rules:
        rule_resp = httpx.post(
            f"{base_url}/v1/mesh/egress-rules",
            json=rule,
            headers=mesh_headers,
            timeout=10.0,
        )
        if rule_resp.status_code == 201:
            print(f"  Egress rule: {rule['agent_name']} {rule['url_pattern']} -> {rule['action']}")
        else:
            print(f"  Egress rule: {rule_resp.status_code} {rule_resp.text}")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n--- Summary ---")
    agents = [
        ("Customer", customer),
        ("Auth", auth),
        ("KYC", kyc),
        ("Credit", credit),
        ("Core Banking", core_banking),
        ("Compliance", compliance),
    ]
    for name, agent in agents:
        print(f"  {name}: {agent.get('id', 'FAILED')} [DRAFT]")
    print(f"  Mesh policies: {priority + 1} created (hub-and-spoke + default deny)")
    print("\nAgents created as DRAFT. Pipeline will submit them next.")


if __name__ == "__main__":
    main()
