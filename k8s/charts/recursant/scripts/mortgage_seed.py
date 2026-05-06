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
    svc_prefix = os.environ.get("SERVICE_PREFIX", "")  # e.g. "recursant-"
    print(f"Seeding mortgage demo agents at {base_url} (service prefix: '{svc_prefix}')")

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
            "url": f"http://{svc_prefix}agents-customer:5020/a2a",
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
            "url": f"http://{svc_prefix}agents-customer:5021/a2a",
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
            "url": f"http://{svc_prefix}n8n-kyc:5022/a2a",
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
            "url": f"http://{svc_prefix}agents-kyc-credit:5023/a2a",
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
            "url": f"http://{svc_prefix}agents-core-banking:5024/a2a",
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
            "url": f"http://{svc_prefix}agents-compliance:5025/a2a",
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
    # Tool Governance — register tools, approve, assign to agents
    # ---------------------------------------------------------------
    print("\n--- Tool Governance ---")

    stub_api_base = "http://recursant-stub-apis:6000"
    mcp_prefix = f"{svc_prefix}mcp" if svc_prefix else "mcp"

    tools_config = [
        {
            "name": "verify_customer",
            "description": "Verify customer BAN and PIN against Customer Master",
            "endpoint_url": f"{stub_api_base}/customer-master/verify",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-customer-master:8080/sse",
            "mcp_server_name": "Customer Master",
            "mcp_server_description": "MCP server for Customer Master system — verifies customer credentials",
            "backend_services": [{"url": f"{stub_api_base}/customer-master/verify", "method": "POST", "description": "Customer Master verification API"}],
            "assign_to": "Authentication Agent",
        },
        {
            "name": "verify_identity",
            "description": "Verify customer identity documents for KYC",
            "endpoint_url": f"{stub_api_base}/kyc/verify-identity",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-kyc-system:8081/sse",
            "mcp_server_name": "KYC System",
            "mcp_server_description": "MCP server for KYC system — verifies identity documents",
            "backend_services": [{"url": f"{stub_api_base}/kyc/verify-identity", "method": "POST", "description": "KYC identity verification API"}],
            "assign_to": "KYC Agent",
        },
        {
            "name": "assess_credit_capacity",
            "description": "Assess credit capacity from annual salary",
            "endpoint_url": f"{stub_api_base}/credit/assess-capacity",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-credit-engine:8082/sse",
            "mcp_server_name": "Credit Engine",
            "mcp_server_description": "MCP server for Credit Engine — assesses credit capacity and makes lending decisions",
            "backend_services": [{"url": f"{stub_api_base}/credit/assess-capacity", "method": "POST", "description": "Credit capacity assessment API"}],
            "assign_to": "Credit Agent",
        },
        {
            "name": "make_credit_decision",
            "description": "Make lending decision based on LTV ratio",
            "endpoint_url": f"{stub_api_base}/credit/decide",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-credit-engine:8082/sse",
            "mcp_server_name": "Credit Engine",
            "mcp_server_description": "MCP server for Credit Engine — assesses credit capacity and makes lending decisions",
            "backend_services": [{"url": f"{stub_api_base}/credit/decide", "method": "POST", "description": "Credit decision API"}],
            "assign_to": "Credit Agent",
        },
        {
            "name": "disburse_loan",
            "description": "Disburse approved mortgage loan",
            "endpoint_url": f"{stub_api_base}/core-banking/disburse",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-core-banking:8083/sse",
            "mcp_server_name": "Core Banking",
            "mcp_server_description": "MCP server for Core Banking system — handles loan disbursement",
            "backend_services": [{"url": f"{stub_api_base}/core-banking/disburse", "method": "POST", "description": "Loan disbursement API"}],
            "assign_to": "Core Banking Agent",
        },
        {
            "name": "check_lending_regulations",
            "description": "Check mortgage lending regulations including LTV and DTI ratio compliance",
            "endpoint_url": f"{stub_api_base}/compliance/check-regulations",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-compliance-engine:8084/sse",
            "mcp_server_name": "Compliance Engine",
            "mcp_server_description": "MCP server for Compliance Engine — regulatory checks for mortgage applications",
            "backend_services": [{"url": f"{stub_api_base}/compliance/check-regulations", "method": "POST", "description": "Lending regulations check API"}],
            "assign_to": "Compliance Crew",
        },
        {
            "name": "verify_document_completeness",
            "description": "Check that all required documents have been provided for the mortgage application",
            "endpoint_url": f"{stub_api_base}/compliance/verify-documents",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-compliance-engine:8084/sse",
            "mcp_server_name": "Compliance Engine",
            "mcp_server_description": "MCP server for Compliance Engine — regulatory checks for mortgage applications",
            "backend_services": [{"url": f"{stub_api_base}/compliance/verify-documents", "method": "POST", "description": "Document completeness check API"}],
            "assign_to": "Compliance Crew",
        },
        {
            "name": "calculate_compliance_score",
            "description": "Calculate a compliance score based on review findings",
            "endpoint_url": f"{stub_api_base}/compliance/calculate-score",
            "http_method": "POST",
            "mcp_server_url": f"http://{mcp_prefix}-compliance-engine:8084/sse",
            "mcp_server_name": "Compliance Engine",
            "mcp_server_description": "MCP server for Compliance Engine — regulatory checks for mortgage applications",
            "backend_services": [{"url": f"{stub_api_base}/compliance/calculate-score", "method": "POST", "description": "Compliance score calculation API"}],
            "assign_to": "Compliance Crew",
        },
    ]

    for tool_cfg in tools_config:
        assign_to = tool_cfg.pop("assign_to")

        # Create tool
        create_resp = httpx.post(
            f"{base_url}/v1/mesh/tools",
            json=tool_cfg,
            headers=headers,
            timeout=10.0,
        )
        if create_resp.status_code == 201:
            tool = create_resp.json()
            print(f"  Created tool: {tool['name']} (id={tool['id']})")
        elif create_resp.status_code == 409:
            print(f"  Tool '{tool_cfg['name']}' already exists, skipping")
            continue
        else:
            print(f"  ERROR creating tool: {create_resp.status_code} {create_resp.text}")
            continue

        tool_id = tool["id"]

        # Approve
        approve_resp = httpx.post(
            f"{base_url}/v1/mesh/tools/{tool_id}/approve",
            headers=headers,
            timeout=10.0,
        )
        if approve_resp.status_code == 200:
            print(f"  Approved: {tool_cfg['name']}")
        else:
            print(f"  Approve failed: {approve_resp.status_code} {approve_resp.text}")

        # Assign to agent
        assign_resp = httpx.post(
            f"{base_url}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": assign_to},
            headers=headers,
            timeout=10.0,
        )
        if assign_resp.status_code == 201:
            print(f"  Assigned: {tool_cfg['name']} -> {assign_to}")
        else:
            print(f"  Assign failed: {assign_resp.status_code} {assign_resp.text}")

    # ---------------------------------------------------------------
    # Egress rules — allow stub APIs, deny everything else
    # ---------------------------------------------------------------
    print("\n--- Egress Rules ---")

    egress_rules = [
        {
            "agent_name": "*",
            "url_pattern": f"{stub_api_base}/*",
            "action": "allow",
            "priority": 0,
        },
        {
            "agent_name": "*",
            "url_pattern": "*",
            "action": "deny",
            "priority": 100,
        },
    ]

    for rule in egress_rules:
        rule_resp = httpx.post(
            f"{base_url}/v1/mesh/egress-rules",
            json=rule,
            headers=mesh_headers,
            timeout=10.0,
        )
        if rule_resp.status_code == 201:
            print(f"  Egress rule: {rule['agent_name']} {rule['action']} {rule['url_pattern']}")
        else:
            print(f"  Egress rule failed: {rule_resp.status_code} {rule_resp.text}")

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
    print(f"  Tools: {len(tools_config)} created, approved, assigned")
    print(f"  Egress rules: {len(egress_rules)} created")
    print("\nAgents created as DRAFT. Pipeline will submit them next.")


if __name__ == "__main__":
    main()
