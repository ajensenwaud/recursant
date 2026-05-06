# Agent Registry Submission API

This document provides instructions on how to create a new agent in the agent registry via the Submission API.

## Create a New Agent

To create a new agent, you must send a `POST` request to the `/api/agents` endpoint. The request body must contain a JSON object with the agent's metadata.

**Endpoint:** `POST /api/agents`

**Headers:**

*   `Content-Type: application/json`
*   `X-User-ID`: (Optional) The ID of the user creating the agent. Defaults to `anonymous`.
*   `X-Tenant-ID`: (Optional) The ID of the tenant. Defaults to `default`.

### JSON Payload

The JSON payload must conform to the `AgentCreateSchema`. Here is an example of a valid payload:

```json
{
    "name": "My Awesome Agent",
    "version": "1.0.0",
    "description": "An agent that does awesome things.",
    "owner_id": "user-123",
    "team_id": "team-456",
    "contact_email": "contact@example.com",
    "classification": "INTERNAL",
    "data_sensitivity": "CONFIDENTIAL",
    "risk_tier": "HIGH",
    "capabilities": [
        {
            "name": "do_awesome_thing",
            "description": "Performs an awesome action.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string"
                    }
                }
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "result": {
                        "type": "string"
                    }
                }
            }
        }
    ],
    "endpoint": {
        "type": "HTTP",
        "url": "https://example.com/agent",
        "auth_method": "API_KEY",
        "timeout_ms": 10000,
        "agent_protocol": "A2A"
    },
    "tools": [
        {
            "tool_id": "calculator",
            "required": true
        }
    ],
    "upstream_agents": [],
    "downstream_agents": [],
    "guardrail_profile_id": "gp-123",
    "execution_graph_id": "eg-456",
    "resource_quota": {
        "max_tokens_per_request": 1000,
        "max_requests_per_minute": 60,
        "max_cost_per_day_usd": 10.50
    }
}
```

### `curl` Example

Here is an example of how to create a new agent using `curl`:

```bash
curl -X POST http://localhost:5000/api/agents \
-H "Content-Type: application/json" \
-H "X-User-ID: user-123" \
-H "X-Tenant-ID: my-tenant" \
-d 
{
    "name": "My Awesome Agent",
    "version": "1.0.0",
    "description": "An agent that does awesome things.",
    "owner_id": "user-123",
    "team_id": "team-456",
    "contact_email": "contact@example.com",
    "classification": "INTERNAL",
    "data_sensitivity": "CONFIDENTIAL",
    "risk_tier": "HIGH",
    "capabilities": [
        {
            "name": "do_awesome_thing",
            "description": "Performs an awesome action.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string"
                    }
                }
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "result": {
                        "type": "string"
                    }
                }
            }
        }
    ],
    "endpoint": {
        "type": "HTTP",
        "url": "https://example.com/agent",
        "auth_method": "API_KEY"
    }
}
```

### Response

If the agent is created successfully, the API will return a `201 Created` status code and a JSON object representing the newly created agent.

If there is an error, the API will return an appropriate error code (e.g., `400`, `409`) and a JSON object with details about the error.
