#!/usr/bin/env python3
"""
Seed script to create 10 agent submissions via the API.

All agents point to the test-agent endpoint used in e2e integration tests.

Usage:
    python scripts/seed_agents.py
    python scripts/seed_agents.py --api-url http://localhost:5000
    python scripts/seed_agents.py --agent-url http://test-agent:5001/invoke
"""

import argparse
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_auth_headers

AGENTS = [
    {
        "name": "customer-360-agent",
        "version": "2.1.0",
        "description": "Retrieves customer profile, account information, and transaction history for support workflows.",
        "owner_id": "svc-customer-team",
        "team_id": "customer-experience",
        "contact_email": "cx-team@recursant.io",
        "classification": "confidential",
        "data_sensitivity": "pii",
        "risk_tier": "high",
        "capabilities": [
            {"name": "customer-lookup", "description": "Look up customer profile by ID, email, or phone number"},
            {"name": "transaction-history", "description": "Fetch transaction history for a customer account"},
        ],
    },
    {
        "name": "invoice-generation-agent",
        "version": "1.0.0",
        "description": "Generates PDF invoices from order data and sends them to customers.",
        "owner_id": "svc-billing",
        "team_id": "finance",
        "contact_email": "billing@recursant.io",
        "classification": "internal",
        "data_sensitivity": "financial",
        "risk_tier": "medium",
        "capabilities": [
            {"name": "invoice-generation", "description": "Generate a PDF invoice from order details"},
        ],
    },
    {
        "name": "compliance-checker-agent",
        "version": "3.0.1",
        "description": "Checks documents and communications against regulatory compliance rules (GDPR, SOX, HIPAA).",
        "owner_id": "svc-compliance",
        "team_id": "legal-compliance",
        "contact_email": "compliance@recursant.io",
        "classification": "restricted",
        "data_sensitivity": "pii",
        "risk_tier": "critical",
        "capabilities": [
            {"name": "gdpr-check", "description": "Validate content for GDPR compliance"},
            {"name": "sox-audit", "description": "Check financial reporting against SOX requirements"},
        ],
    },
    {
        "name": "knowledge-base-search-agent",
        "version": "1.2.0",
        "description": "Semantic search over the company knowledge base for internal support and onboarding.",
        "owner_id": "svc-knowledge",
        "team_id": "engineering-platform",
        "contact_email": "platform@recursant.io",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [
            {"name": "kb-search", "description": "Search the knowledge base using natural language queries"},
            {"name": "article-summary", "description": "Summarise a knowledge base article"},
        ],
    },
    {
        "name": "incident-triage-agent",
        "version": "1.0.0",
        "description": "Automatically triages production incidents by analysing logs, metrics, and alerts.",
        "owner_id": "svc-sre",
        "team_id": "site-reliability",
        "contact_email": "sre@recursant.io",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "medium",
        "capabilities": [
            {"name": "incident-classification", "description": "Classify incident severity from alert data"},
            {"name": "root-cause-suggestion", "description": "Suggest probable root causes based on logs and metrics"},
        ],
    },
    {
        "name": "hr-onboarding-agent",
        "version": "2.0.0",
        "description": "Guides new employees through onboarding tasks, document submission, and system access requests.",
        "owner_id": "svc-hr",
        "team_id": "human-resources",
        "contact_email": "hr-tech@recursant.io",
        "classification": "confidential",
        "data_sensitivity": "pii",
        "risk_tier": "medium",
        "capabilities": [
            {"name": "onboarding-checklist", "description": "Generate and track onboarding task checklist for new hires"},
            {"name": "access-request", "description": "Submit system access requests on behalf of new employees"},
        ],
    },
    {
        "name": "code-review-agent",
        "version": "1.5.0",
        "description": "Performs automated code review on pull requests, checking for security issues and style violations.",
        "owner_id": "svc-devtools",
        "team_id": "developer-experience",
        "contact_email": "devtools@recursant.io",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [
            {"name": "security-review", "description": "Scan code changes for common security vulnerabilities"},
            {"name": "style-check", "description": "Check code against team style guidelines"},
        ],
    },
    {
        "name": "data-pipeline-monitor-agent",
        "version": "1.1.0",
        "description": "Monitors data pipeline health and alerts on schema drift, data quality issues, and SLA breaches.",
        "owner_id": "svc-data-eng",
        "team_id": "data-engineering",
        "contact_email": "data-eng@recursant.io",
        "classification": "internal",
        "data_sensitivity": "financial",
        "risk_tier": "high",
        "capabilities": [
            {"name": "pipeline-health", "description": "Check health status of data pipelines"},
            {"name": "schema-drift-detection", "description": "Detect schema changes in upstream data sources"},
        ],
    },
    {
        "name": "sales-forecast-agent",
        "version": "1.0.0",
        "description": "Generates sales forecasts by analysing CRM data, market trends, and historical performance.",
        "owner_id": "svc-sales-ops",
        "team_id": "sales-operations",
        "contact_email": "sales-ops@recursant.io",
        "classification": "confidential",
        "data_sensitivity": "financial",
        "risk_tier": "medium",
        "capabilities": [
            {"name": "revenue-forecast", "description": "Generate quarterly revenue forecasts from CRM data"},
        ],
    },
    {
        "name": "chatbot-support-agent",
        "version": "4.2.1",
        "description": "Customer-facing chatbot handling FAQs, order status inquiries, and basic troubleshooting.",
        "owner_id": "svc-support",
        "team_id": "customer-support",
        "contact_email": "support-eng@recursant.io",
        "classification": "public",
        "data_sensitivity": "pii",
        "risk_tier": "high",
        "capabilities": [
            {"name": "faq-answering", "description": "Answer frequently asked customer questions"},
            {"name": "order-status", "description": "Look up and report order delivery status"},
            {"name": "troubleshooting", "description": "Guide customers through basic product troubleshooting"},
        ],
    },
]


def seed_agents(api_url: str, agent_url: str) -> None:
    headers = get_auth_headers(api_url)

    endpoint_types = ["langchain", "langgraph", "crewai", "openai", "custom"]
    auth_methods = ["api_key", "oauth2", "mtls"]

    created = 0
    for i, agent_data in enumerate(AGENTS):
        payload = {
            **agent_data,
            "endpoint": {
                "type": endpoint_types[i % len(endpoint_types)],
                "url": agent_url,
                "auth_method": auth_methods[i % len(auth_methods)],
                "timeout_ms": 60000,
                "agent_protocol": "A2A",
            },
        }

        resp = requests.post(f"{api_url}/v1/agents", headers=headers, json=payload)
        if resp.status_code == 201:
            agent = resp.json()
            agent_id = agent["id"]
            created += 1
            print(f"  [{created}/10] Created: {agent['name']} (id={agent_id[:8]}...)")

            # Submit the agent, which auto-triggers security scanning
            # This can take a while as it runs all security tests synchronously
            print(f"           Submitting (runs security scan, may take ~2 min)...")
            try:
                submit_resp = requests.post(
                    f"{api_url}/v1/agents/{agent_id}/submit", headers=headers,
                    timeout=300
                )
                if submit_resp.status_code == 200:
                    result = submit_resp.json()
                    print(f"           Submitted -> status: {result.get('status', 'unknown')}")
                else:
                    print(f"           Submit failed: {submit_resp.status_code}", file=sys.stderr)
            except requests.exceptions.Timeout:
                print(f"           Submit timed out (scan may still be running in background)")
        else:
            print(f"  FAILED: {agent_data['name']} - {resp.status_code}: {resp.text}", file=sys.stderr)

    print(f"\nDone: {created}/10 agents created and submitted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed 10 agent submissions")
    parser.add_argument("--api-url", default="http://localhost:5000", help="Registry API base URL")
    parser.add_argument("--agent-url", default="http://test-agent:5001/invoke", help="Test agent invoke endpoint")
    args = parser.parse_args()

    print(f"Seeding agents against {args.api_url}")
    print(f"Agent endpoint: {args.agent_url}\n")
    seed_agents(args.api_url, args.agent_url)
