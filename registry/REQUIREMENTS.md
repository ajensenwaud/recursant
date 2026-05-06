# Recursant Agent Registry - Base Requirements

## Overview

The Agent Registry is a core component of the Recursant agentic mesh platform. It provides a centralised catalogue for submitting, security testing, evaluating, approving, and discovering AI agents across the enterprise. 

The registry ensures that only vetted, policy-compliant agents can participate in the mesh, while enabling other agents and systems to discover agents by capability.

**Key Functions:**
1. **Submission** - Onboard new agents with metadata, configuration, and ownership
2. **Security Assessment** - Automated vulnerability scanning and threat assessment
3. **Evaluation** - Guardrails compliance testing using LLM-as-a-judge techniques
4. **Approval** - Workflow-driven approval with human oversight
5. **Discovery** - Semantic and attribute-based search and discovery of agents, which allows agents to discover other agent dynamically using the A2A protocol
6. **Web interface** - A web interface for viewing submissions, viewing and managing security assessments, viewing and managing evaluations, and approving submisssions once they have passed security assessment evaluation

---

## 1. Agent Submission

### 1.1 Agent Metadata Schema

```yaml
agent:
  # Identity
  id: string                    # UUID, system-generated
  name: string                  # Human-readable name (unique within tenant)
  version: semver               # Semantic version (e.g., 1.2.3)
  description: string           # Free-text description
  
  # Ownership
  owner_id: string              # User or service account ID
  team_id: string               # Owning team/department
  contact_email: string         # Escalation contact
  
  # Classification
  classification: enum          # internal | confidential | restricted | public
  data_sensitivity: enum        # none | pii | phi | financial | secret
  risk_tier: enum               # low | medium | high | critical
  
  # Capabilities (for discovery)
  capabilities:
    - name: string              # e.g., "customer-lookup", "invoice-generation"
      description: string       # Natural language description for semantic matching
      input_schema: json_schema # Expected input format
      output_schema: json_schema # Expected output format
      
  # Technical Configuration
  endpoint:
    type: enum                  # langchain | crewai | langgraph | agentforce | databricks | openai | custom
    url: string                 # Invocation endpoint
    auth_method: enum           # mtls | oauth2 | api_key | iam
    timeout_ms: integer         # Request timeout
    agent_protocol: string      # A2A
    
  # Dependencies
  tools:
    - tool_id: string           # Reference to Tool Registry
      required: boolean
  upstream_agents:
    - agent_id: string          # Agents this agent may call
  downstream_agents:
    - agent_id: string          # Agents permitted to call this agent
      
  # Governance
  guardrail_profile_id: string  # Reference to guardrail configuration
  execution_graph_id: string    # Reference to permitted execution paths
  resource_quota:
    max_tokens_per_request: integer
    max_requests_per_minute: integer
    max_cost_per_day_usd: decimal
```

### 1.2 Submission API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/agents` | POST | Submit new agent for review |
| `/v1/agents/{id}` | PUT | Update existing agent (triggers re-evaluation) |
| `/v1/agents/{id}` | GET | Retrieve agent details |
| `/v1/agents/{id}` | DELETE | Decommission agent (soft delete) |
| `/v1/agents/{id}/versions` | GET | List all versions of an agent |
| `/v1/agents/{id}/versions/{version}` | GET | Retrieve specific version |

### 1.3 Submission Validation Rules

- **REQ-SUB-001**: All required fields must be populated
- **REQ-SUB-002**: Agent name must be unique within tenant namespace
- **REQ-SUB-003**: Version must follow semantic versioning (MAJOR.MINOR.PATCH)
<!---
- **REQ-SUB-005**: Owner must have valid identity in identity provider
-->
- **REQ-SUB-006**: At least one capability must be defined
- **REQ-SUB-007**: Guardrail profile must exist and be active
<!--- - **REQ-SUB-008**: All referenced tools must exist in Tool Registry 
- **REQ-SUB-009**: Cryptographic signature of agent package required for non-SaaS deployments -->

---

## 2. Security Testing

### 2.1 Automated Security Scans
This capabiliity conducts automated security scans of an agent.
Agents are submitted by pointing to the URL of a running agent, which the registry will then test.

| Scan Type | Description | Blocking |
|-----------|-------------|----------|
| **Prompt Injection Resistance** | Test agent against known prompt injection patterns (direct, indirect, jailbreaks) | Yes |
| **Data Exfiltration Check** | Verify agent does not leak sensitive data in outputs | Yes |
| **Tool Abuse Testing** | Confirm agent cannot misuse tools beyond declared permissions | Yes |
| **Egress Validation** | Verify agent only calls declared endpoints/services | Yes |
| **Credential Handling** | Check for hardcoded secrets, improper credential storage | Yes |
| **Input Validation** | Test handling of malformed, oversized, or malicious inputs | Yes |
| **Dependency Scan** | Check for vulnerable dependencies (CVEs) | Configurable |
| **Container/Runtime Scan** | Scan execution environment for vulnerabilities | Configurable |

### 2.2 Security Test Requirements

- **REQ-SEC-001**: All blocking scans must pass before agent proceeds to evaluation
- **REQ-SEC-002**: Prompt injection tests must include OWASP LLM Top 10 attack patterns
- **REQ-SEC-003**: Security scan results must be signed and stored for audit
- **REQ-SEC-004**: Failed scans must generate detailed remediation guidance
- **REQ-SEC-005**: Re-submission after failure must reference original scan ID
- **REQ-SEC-006**: Security test suite must be versioned and updates applied to pending submissions
- **REQ-SEC-007**: Custom security policies per risk tier (critical agents get more rigorous testing)
- **REQ-SEC-008**: Integration with external vulnerability databases (NVD, OSV)

### 2.3 Security Scan API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/agents/{id}/security-scans` | POST | Trigger manual security scan |
-->
| `/v1/agents/{id}/security-scans` | GET | List security scan history |
| `/v1/agents/{id}/security-scans/{scan_id}` | GET | Retrieve scan results |
| `/v1/security-policies` | GET | List available security policies |
| `/v1/security-policies/{id}` | GET | Retrieve policy details |

---

## 3. Guardrails Evaluation

### 3.1 Evaluation Framework

Agents must pass the guardrails evaluation to ensure they operate within defined safety and compliance boundaries. Evaluation uses LLM-as-a-judge techniques with domain-specific test suites.

**Evaluation Dimensions:**

| Dimension | Description | Weight |
|-----------|-------------|--------|
| **Safety** | Agent avoids harmful, dangerous, or unethical outputs | Critical |
| **Policy Compliance** | Agent adheres to organisation-specific policies | Critical |
| **Hallucination Resistance** | Agent does not fabricate information | High |
| **Boundary Adherence** | Agent stays within declared capabilities | High |
| **Output Quality** | Agent produces accurate, relevant responses | Medium |

### 3.2 Evaluation Test Suites

```yaml
evaluation_suite:
  id: string
  name: string
  description: string
  applicable_risk_tiers: [low, medium, high, critical]
  
  test_cases:
    - id: string
      category: enum           # safety | policy | hallucination | boundary | quality | tone
      name: string
      description: string
      input_prompt: string
      expected_behavior: string # Natural language description for LLM judge
      grading_criteria:
        - criterion: string
          weight: decimal
      passing_threshold: decimal  # 0.0 to 1.0
      
  judge_config:
    model: string              # Model to use as judge (e.g., claude-4.5-opus
    temperature: decimal
    system_prompt: string      # Instructions for judge
```

### 3.3 Evaluation Requirements

- **REQ-EVAL-001**: All agents must pass the baseline evaluation suite
- **REQ-EVAL-002**: High/critical risk tier agents must pass extended evaluation suite
<!---- **REQ-EVAL-003**: Evaluation must include domain-specific test cases based on agent capabilities -->
- **REQ-EVAL-004**: Evaluation results must include per-test-case scores and reasoning
- **REQ-EVAL-005**: Failed evaluations must identify specific failing test cases
- **REQ-EVAL-006**: Evaluation evidence must be cryptographically signed for audit
<!--- - **REQ-EVAL-007**: Re-evaluation required on agent update (version change) -->
<!--- **REQ-EVAL-008**: Continuous evaluation in production (periodic re-testing) -->
<!--- **REQ-EVAL-009**: Support for custom evaluation suites per team/use case -->

### 3.4 Evaluation API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/agents/{id}/evaluations` | POST | Trigger evaluation |
| `/v1/agents/{id}/evaluations` | GET | List evaluation history |
| `/v1/agents/{id}/evaluations/{eval_id}` | GET | Retrieve evaluation results |
| `/v1/evaluation-suites` | GET | List available evaluation suites |
| `/v1/evaluation-suites` | POST | Create custom evaluation suite |
| `/v1/evaluation-suites/{id}` | GET | Retrieve suite details |
| `/v1/evaluation-suites/{id}/test-cases` | POST | Add test case to suite |

---

## 4. Approval Workflow

### 4.1 Approval States

```
┌──────────┐     ┌──────────────┐     ┌────────────┐     ┌──────────────┐     ┌──────────┐
│ DRAFT    │────▶│ SUBMITTED    │────▶│ TESTING    │────▶│ EVALUATING   │────▶│ PENDING  │
└──────────┘     └──────────────┘     └────────────┘     └──────────────┘     │ APPROVAL │
                                            │                   │              └────┬─────┘
                                            ▼                   ▼                   │
                                     ┌──────────────┐   ┌──────────────┐            │
                                     │ SECURITY     │   │ EVALUATION   │            │
                                     │ FAILED       │   │ FAILED       │            │
                                     └──────────────┘   └──────────────┘            │
                                                                                    ▼
                       ┌──────────┐                                          ┌──────────┐
                       │ REJECTED │◀────────────────────────────────────────│ APPROVED │
                       └──────────┘                                          └────┬─────┘
                                                                                  │
                                                                                  ▼
                       ┌──────────────┐     ┌──────────┐     ┌──────────────────────────┐
                       │ DECOMMISSIONED│◀────│ SUSPENDED│◀────│ ACTIVE (in registry)     │
                       └──────────────┘     └──────────┘     └──────────────────────────┘
```

### 4.2 Approval Roles

| Role | Permissions |
|------|-------------|
| **Agent Owner** | Submit, update, view own agents |
| **Team Lead** | Approve low/medium risk agents for own team |
| **Security Reviewer** | Review security scan results, override security failures (with justification) |
| **Governance Board** | Approve high/critical risk agents, define policies |
| **Platform Admin** | Suspend/decommission agents, manage global policies |

### 4.3 Approval Requirements

- **REQ-APR-001**: Low risk agents require Team Lead approval
- **REQ-APR-002**: Medium risk agents require Team Lead + Security Reviewer approval
- **REQ-APR-003**: High risk agents require Governance Board approval
- **REQ-APR-004**: Critical risk agents require Governance Board + Security Reviewer + CISO approval
- **REQ-APR-005**: All approvals must include justification comment, which is a mandatory field for audit purposes
<!--- **REQ-APR-006**: Approvals must be time-bound (default: 12 months, then re-approval required) -->
<!--- **REQ-APR-007**: Approval can be delegated but delegation must be audited -->
<!--- **REQ-APR-008**: Emergency approval path for critical business needs (with post-hoc review) -->
**REQ-APR-009**: Approvals can be viewed via a web interface, so agent owners can check progress

### 4.4 Approval API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/agents/{id}/approval` | POST | Submit approval decision |
| `/v1/agents/{id}/approval` | GET | Get current approval status |
| `/v1/agents/{id}/approval/history` | GET | List approval history |
| `/v1/approvals/pending` | GET | List agents pending approval (for current user's role) |
| `/v1/agents/{id}/suspend` | POST | Suspend active agent |
| `/v1/agents/{id}/reinstate` | POST | Reinstate suspended agent |

---

## 5. Agent Discovery

### 5.1 Discovery Methods

The registry supports multiple discovery mechanisms to enable agents to find other agents with specific capabilities and skills:

**5.1.1 Attribute-Based Search**
- Search by name, team, classification, risk tier, status
- Filter by capability name, tool dependencies, skills
- Filter by endpoint type (e.g., "all LangChain agents, all LangGraph agents")

**5.1.2 Semantic Capability Search**
- Natural language query matched against capability descriptions
- Powered by vector similarity search
- Returns ranked results by relevance score

**5.1.3 Schema-Based Matching**
- Find agents whose input/output schemas are compatible
- Supports exact match and structural compatibility

### 5.2 Discovery Requirements

<!--- - **REQ-DIS-001**: Semantic search must return results within 100ms (p95) -->
- **REQ-DIS-002**: Only ACTIVE agents are discoverable (unless explicitly searching other states)
- **REQ-DIS-003**: Discovery results must respect data classification (agents only see what they're authorised for)
- **REQ-DIS-004**: Results must include agent health status (healthy, degraded, unhealthy)
- **REQ-DIS-005**: Capability embeddings must be updated when agent capabilities change
-->
- **REQ-DIS-006**: Support pagination for large result sets
- **REQ-DIS-007**: Discovery audit log (who searched for what, when)
- **REQ-DIS-009**: Version resolution (return specific version or latest stable)
- **REQ-DIS-010**: Schema compatibility scoring (0-100% match)

### 5.3 Discovery API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/agents/search` | POST | Attribute-based search |
| `/v1/agents/discover` | POST | Semantic capability search |
| `/v1/agents/match` | POST | Schema-based compatibility matching |
| `/v1/agents/{id}/health` | GET | Get agent health status |
<!---| `/v1/agents/{id}/invoke-info` | GET | Get invocation details (endpoint, auth) | -->

### 5.4 Discovery Request/Response

**Semantic Discovery Request:**
```json
{
  "query": "agent that can look up customer account details and transaction history",
  "filters": {
    "status": ["ACTIVE"],
    "classification": ["internal", "confidential"],
    "risk_tier": ["low", "medium"],
    "endpoint_type": ["langchain", "langgraph"]
  },
  "limit": 10,
  "include_health": true
}
```

**Discovery Response:**
```json
{
  "results": [
    {
      "agent_id": "agt_abc123",
      "name": "customer-360-agent",
      "version": "2.1.0",
      "relevance_score": 0.94,
      "matching_capabilities": [
        {
          "name": "customer-lookup",
          "description": "Retrieves customer profile and account information",
          "match_score": 0.97
        },
        {
          "name": "transaction-history",
          "description": "Fetches transaction history for a customer account",
          "match_score": 0.91
        }
      ],
      "health": {
        "status": "healthy",
        "latency_p95_ms": 245,
        "error_rate_1h": 0.002
      },
      "invoke_info": {
        "endpoint_type": "langchain",
        "auth_method": "mtls",
        "agent_protocol": "a2a"
      }
    }
  ],
  "total_count": 3,
  "query_time_ms": 47
}
```
---
## 6. Web interface 
Recursant Registry must have a web interface, which allows an admin to log in and perform the following activities:

### 6.1 Submissions
**REQ-WEB-001**: Viewing submissions
**REQ-WEB-002**: Deleting submissions (i.e. if they are inappropriate)

### 6.2 Security Assessments
**REQ-WEB-003**: Viewing the outcome of security assessments against submissions
**REQ-WEB-004: Manually triggering a re-run of security assessments against a submission

### 6.3 Evaluations
**REQ-WEB-005**: Viewing the outcome of evaluations against submissions
**REQ-WEB-006**: Editing and configuring evaluation rules
**REQ-WEB-007** Manually triggering re-run of an evaluation against a submission

### 6.4 Approvals
**REQ-WEB-008**: Viewing the list of submissions that have passed the security assessments and evaluations
**REQ-WEB-009**: Approving and declining submissions

### 6.5 Guardrail enforcement (First round)
Context: the registry needs a dynamic way of enforcing guardrails on all the agents in the mesh. A guardrail is a safety mechanism that prevents harmful outputs and eensures adherence to ethical and regulatory standards. Safeguaards are critical to mitigate model risks such as hallucinations, data leaks, prompt injection, bias, etc. The followign needs to be implemented: 

- Facility in the registry to define, edit, delete, and approve guardrails including type (pre-processing, post-processing, system / structural guardrails)
    - Pre-processing guardrails validate and sanitise user queries before they reach the model, filtering for prompt injection, PII leak, blocked topics
    - Post-processing guardrails monitor responses for bias, factual errors, or redacts content before it is shown to the user
    - System / structural guardrails restrict output formats (e.g. JSON, text) and tool access (i.e. what tools an agent can invoke)
- Ability to test the guardrails against one or more agents in the mesh in realtime 
- Pre-processing guardails as per requirements above, implemented using the sidecar and an LLM-as-judge, lightweight/non-LLM checkers using vector db lookup, or ML classifiers/regex for PII identification
- Post-processing guardraisl as per requirements above, implemented using the sidecar and an LLM-as-judge, lightweight/non-LLM checkers using a vector db to identify bias/toxicity
- User can define the guardrail configuration (LLM, lightweight, ML) on the agent level via the UI
- Existing sidecar policy framework implements structural guardrails (e.g. tool use)
- Configuration for now is via API with UI on top. Configuration files to be defined later.
- Guardrails are either in draft mode (for testing) or active
- Guardrails can be enforced for a subset of agents or the full cohort
- Guardrail changes are automatically pushed to sidecards in real-time (real-time enforcement)

### 6.6 Guardrail enforcement (second round) 
There is a need to add additional guardrail capabiltity to Recursat. The following feautures neeed to be dded: 

- Chain of thought auditing (as per Meta's LlamaFirewall), which adds capabiltiy to audit and agent's trace, not just the output. This would require a post-processing step that inspects the intermediate steps (tool calls, retreval results, decision points) for manipulation, goal hijacking, prompt injection hidden in retrieved documents. Reasoning-level inspection should be added to the hash-chained audit logs in Recursant. 
- Guardrail observability dashboard: A graphical dashboard in the registry that shows guardrail trigger rates per agent, false positive trends, latency breakdown by mechanism (regex vs vector vs LLM-as-judge), top blocked patterns, and drift detection (e.g. guardrail effectiveness degrading over time). 
- Adversarial testintg: automatically generate adversarial inptus (jail breaks, injection variants, encoding ticks) and test them against active guardrails, reporting evasion rates. This should be part of the existing security testing infrastrucure. The adversarial testing can be run as a one-off or run continously (with a user defined interval) across all agents and reports an alert if agents ddo not meet the standard.
- Custom attack library: Admins can create, edit, delete, and bulk import/export custom adversarial attack entries via the web UI. Custom attacks are stored in the database, organized by attack type category, tagged with severity and source, and merged with the built-in static library during test runs.
- LLM-generated attack variants: When a test suite has generation_config set, the system uses an attacker LLM to dynamically generate novel adversarial inputs. Supports three strategies: mutation (rephrase existing attacks), category-targeted (generate attacks for specific categories informed by guardrail descriptions), and creative (novel techniques like payload splitting, encoding chains). Graceful degradation if LLM fails — runs complete with static + custom inputs only.

### 6.7 Other requirements
**REQ-WEB-010**: The interface must be written in React and look simple and appealing
**REQ-WEB-011**: The interface must providde a simple authentication mechanism allowing admins to log in and log out. There is no need for user management at this stage; this can be added later. Username and password for the admin user is configured in the .env file.

---

## 7. Architecture

### 7.1 Storage Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Agent Catalog** | PostgreSQL | Agent metadata, versioning, ownership, status |
| **Capability Vectors** | pgvector | Semantic search embeddings |
| **Audit Log** | PostgreSQL | All registry operations |
| **Test Results** | Local filesystem (for now) | Security scan and evaluation artifacts |
| **Cache** | Redis | Discovery results, health status |

### 7.2 Runtime
The applicaiton will be built as a monolithic API-based application for now. Later on we will break it into microservices, which will be deployed independently. 

The core language is Python. The application has the following components: 

- Submission, Security Assessment, Evaluation, Approval, and Discovery APIs: Written as RESTful services written using Flask
- Web interface: Build using React running on top of Flask APIs
- All authentication should be built using a Python OAuth2 server framework such as Flask-OAuthlib or similar. Later on, the application can be extended to integrate with 3rd party federated authentication services such as Active Directory or LDAP
- Storage: PostgreSQL for main storage, Redis for caching, pgvector for semantic search
- Runtime: The applicaiton will be deployed in a Docker container with Docker compose as the orchestration framework


### 7.2 Data Retention

| Data Type | Retention Period | Notes |
|-----------|------------------|-------|
| Agent metadata | Indefinite | Soft delete, never purged |
| Security scan results | 7 years | Regulatory requirement |
| Evaluation results | 7 years | Regulatory requirement |
| Approval decisions | 7 years | Regulatory requirement |
| Discovery audit logs | 2 years | Configurable |
| Health metrics | 90 days | Rolling window |



---

## 8. Non-Functional Requirements

### 8.1 Performance
None defined for now
<!--
- **REQ-NFR-001**: Discovery API p95 latency < 100ms
- **REQ-NFR-002**: Submission API p95 latency < 500ms
- **REQ-NFR-003**: Security scan completion < 10 minutes (low/medium risk)
- **REQ-NFR-004**: Evaluation completion < 30 minutes (baseline suite)
- **REQ-NFR-005**: Support 10,000 registered agents per tenant
- **REQ-NFR-006**: Support 1,000 discovery requests per second per tenant 
-->

### 8.2 Availability
<!--
- **REQ-NFR-007**: 99.9% availability for discovery API
- **REQ-NFR-008**: 99.5% availability for submission/approval APIs
- **REQ-NFR-009**: Graceful degradation (cached discovery results if primary unavailable)
-->

### 8.3 Security

- **REQ-NFR-010**: All API endpoints require authentication (OAuth2/OIDC or mTLS)
<!-- - **REQ-NFR-011**: All data encrypted at rest (AES-256) -->
- **REQ-NFR-012**: All data encrypted in transit (TLS 1.3)
- **REQ-NFR-013**: Role-based access control on all operations
- **REQ-NFR-014**: Audit logging for all state changes
- **REQ-NFR-015**: SOC 2 Type II compliant

### 8.4 Compliance

- **REQ-NFR-016**: GDPR-compliant data handling
- **REQ-NFR-018**: Integration with enterprise identity providers (SAML, OIDC)
- **REQ-NFR-019**: Export capability for regulatory reporting

---
<!---
## 8. Integration Points

### 8.1 Internal Integrations
| Component | Integration Type | Purpose |
|-----------|------------------|---------|
| **Mesh Gateway** | REST | Invocation routing based on registry lookups |
| **Audit Service** | Event stream | Publish all registry events |
| **Governance Layer** | REST | Policy enforcement, lineage tracking |
| **Observability Stack** | OpenTelemetry | Metrics, traces, logs | 
| **Tool Registry** | REST | Tool dependency validation | 

### 8.2 External Integrations
| System | Integration Type | Purpose |
|--------|------------------|---------|
| **Identity Provider** | OIDC/SAML | User authentication, group membership |
| **SIEM** | Syslog/Webhook | Security event forwarding |
| **Ticketing System** | Webhook/API | Approval workflow integration |
| **CI/CD Pipeline** | REST API | Automated agent deployment | 
| **Vulnerability Database** | API | CVE checking for dependencies |
-->

---

## 9. Future Considerations

The following capabilities are out of scope for the initial release but should be considered in the architecture:

- **Federation**: Cross-organisation agent discovery (B2B scenarios)
- **Marketplace**: Public/partner agent catalogue
- **Auto-scaling recommendations**: Based on usage patterns
- **Agent lineage**: Full provenance tracking of agent evolution
- **A/B testing**: Canary deployments for agent versions
- **Cost allocation**: Per-agent cost tracking and chargeback

---

## References

This requirements document draws on:

1. **Recursant Architecture** - Agentic mesh architecture discussions (internal)
2. **OWASP LLM Top 10** - Security testing patterns for LLM applications
3. **NIST AI RMF** - AI Risk Management Framework
4. **ISO 42001** - AI Management System standard
5. **EU AI Act** - Regulatory compliance requirements
6. **EvalOps Framework** - Continuous evaluation patterns (evalops.dev)
7. **LangChain/LangGraph** - Agent orchestration patterns
8. **Agent Protocol** - Emerging standard for agent interoperability

---

*Document Version: 0.1.0*  
*Last Updated: 2026-01-23*  
*Status: DRAFT*
