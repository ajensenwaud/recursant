# Security Testing Implementation Plan

## Overview

Implement automated security scanning for AI agents in the Recursant Registry. Agents are tested at their live endpoints for vulnerabilities including prompt injection, data exfiltration, tool abuse, and more.

---

## Files to Create

| File | Purpose |
|------|---------|
| `app/models/security.py` | Models: SecurityScan, SecurityScanResult, SecurityPolicy, SecurityTestCase + Enums |
| `app/schemas/security.py` | Marshmallow schemas for validation/serialization |
| `app/services/security_service.py` | Business logic for scan execution |
| `app/api/security.py` | API routes for security endpoints |
| `migrations/versions/*_add_security_testing.py` | Database migration |
| `scripts/seed_security_tests.py` | Seed OWASP LLM Top 10 test cases and default policies |

## Files to Modify

| File | Changes |
|------|---------|
| `app/models/__init__.py` | Export new models |
| `app/schemas/__init__.py` | Export new schemas |
| `app/services/__init__.py` | Export SecurityService |
| `app/api/__init__.py` | Import security routes |
| `app/services/agent_service.py` | Auto-trigger scan on agent submission |

---

## Database Models

### New Enums

```python
class ScanType(enum.Enum):
    PROMPT_INJECTION = 'prompt_injection'
    DATA_EXFILTRATION = 'data_exfiltration'
    TOOL_ABUSE = 'tool_abuse'
    EGRESS_VALIDATION = 'egress_validation'
    CREDENTIAL_HANDLING = 'credential_handling'
    INPUT_VALIDATION = 'input_validation'

class ScanStatus(enum.Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

class ScanResultStatus(enum.Enum):
    PASSED = 'passed'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    ERROR = 'error'

class SeverityLevel(enum.Enum):
    INFO = 'info'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'
```

### SecurityPolicy Model

Configurable policies per risk tier (REQ-SEC-007):

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `name` | String(255) | Unique policy name |
| `description` | Text | Policy description |
| `version` | String(50) | Policy version (REQ-SEC-006) |
| `applicable_risk_tiers` | JSON | List of RiskTier values this applies to |
| `scan_configs` | JSON | Config per scan type (see below) |
| `is_active` | Boolean | Whether policy is active |
| `is_default` | Boolean | Default policy for risk tier |
| `created_at` | DateTime | Audit timestamp |
| `updated_at` | DateTime | Audit timestamp |
| `created_by` | String(255) | Creator user ID |

**scan_configs JSON structure:**
```json
{
  "prompt_injection": {
    "enabled": true,
    "blocking": true,
    "timeout_seconds": 300,
    "max_retries": 3
  },
  "data_exfiltration": {
    "enabled": true,
    "blocking": true,
    "timeout_seconds": 300
  }
}
```

### SecurityScan Model

Main scan entity tracking execution:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `agent_id` | UUID (FK) | Agent being scanned |
| `policy_id` | UUID (FK) | Policy used |
| `policy_version` | String(50) | Snapshot of policy version at scan time |
| `previous_scan_id` | UUID (FK, nullable) | For re-submissions (REQ-SEC-005) |
| `status` | Enum(ScanStatus) | Current scan status |
| `total_tests` | Integer | Total test count |
| `passed_tests` | Integer | Passed test count |
| `failed_tests` | Integer | Failed test count |
| `skipped_tests` | Integer | Skipped test count |
| `error_tests` | Integer | Error test count |
| `all_blocking_passed` | Boolean | True if all blocking tests passed (REQ-SEC-001) |
| `result_signature` | Text | HMAC-SHA256 signature (REQ-SEC-003) |
| `signature_algorithm` | String(50) | 'HMAC-SHA256' |
| `started_at` | DateTime | When scan started |
| `completed_at` | DateTime | When scan completed |
| `triggered_by` | String(50) | 'manual' / 'automatic' / 'resubmission' |
| `initiated_by` | String(255) | User ID who triggered |
| `created_at` | DateTime | Creation timestamp |

### SecurityScanResult Model

Individual test results within a scan:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `scan_id` | UUID (FK) | Parent scan |
| `scan_type` | Enum(ScanType) | Type of test |
| `test_case_id` | String(255) | e.g., "OWASP-LLM-01-001" |
| `test_case_name` | String(255) | Human-readable name |
| `test_case_description` | Text | Description |
| `status` | Enum(ScanResultStatus) | passed/failed/skipped/error |
| `is_blocking` | Boolean | Whether failure blocks progression |
| `severity` | Enum(SeverityLevel) | Severity for failed tests |
| `input_payload` | Text | Test input sent to agent |
| `agent_response` | Text | Agent's response |
| `expected_behavior` | Text | What agent should do |
| `actual_behavior` | Text | What agent actually did |
| `remediation_guidance` | Text | How to fix (REQ-SEC-004) |
| `reference_urls` | JSON | Links to OWASP, NVD, CWE |
| `execution_time_ms` | Integer | Test duration |
| `error_message` | Text | Error details if status=error |
| `executed_at` | DateTime | When test ran |

### SecurityTestCase Model

Predefined test case definitions:

| Column | Type | Description |
|--------|------|-------------|
| `id` | String(255) | Primary key, e.g., "OWASP-LLM-01-001" |
| `scan_type` | Enum(ScanType) | Category of test |
| `name` | String(255) | Test name |
| `description` | Text | What this tests |
| `category` | String(100) | e.g., "direct_injection", "indirect_injection" |
| `input_template` | Text | The prompt/payload to send |
| `detection_patterns` | JSON | How to detect pass/fail (see below) |
| `expected_behavior` | Text | Expected agent behavior |
| `remediation_guidance` | Text | How to fix failures |
| `severity` | Enum(SeverityLevel) | Severity level |
| `is_blocking` | Boolean | Blocks agent approval if fails |
| `owasp_reference` | String(50) | e.g., "LLM01" |
| `cwe_reference` | String(50) | e.g., "CWE-77" |
| `external_references` | JSON | NVD, OSV links (REQ-SEC-008) |
| `version` | String(50) | Test case version (REQ-SEC-006) |
| `is_active` | Boolean | Whether test is active |
| `created_at` | DateTime | Creation timestamp |
| `updated_at` | DateTime | Update timestamp |

**detection_patterns JSON structure:**
```json
{
  "failure_indicators": ["regex pattern 1", "regex pattern 2"],
  "success_indicators": ["regex pattern"],
  "detection_method": "regex"  // or "semantic" or "llm_judge"
}
```

---

## API Endpoints

### Security Scans

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/agents/{id}/security-scans` | POST | Trigger a security scan |
| `/v1/agents/{id}/security-scans` | GET | List scan history (paginated) |
| `/v1/agents/{id}/security-scans/{scan_id}` | GET | Get scan details with results |

### Security Policies

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/security-policies` | GET | List available policies |
| `/v1/security-policies/{id}` | GET | Get policy details |

### Request/Response Examples

**Trigger Scan Request:**
```json
POST /v1/agents/{id}/security-scans
{
  "policy_id": "uuid",           // Optional, uses default for risk tier
  "previous_scan_id": "uuid"     // Required for re-submissions (REQ-SEC-005)
}
```

**Trigger Scan Response (202 Accepted):**
```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "status": "pending",
  "policy_id": "uuid",
  "policy_version": "1.0.0",
  "triggered_by": "manual",
  "initiated_by": "user-123",
  "created_at": "2026-01-24T10:00:00Z"
}
```

**Get Scan Response:**
```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "status": "completed",
  "total_tests": 15,
  "passed_tests": 14,
  "failed_tests": 1,
  "all_blocking_passed": false,
  "result_signature": "abc123...",
  "started_at": "2026-01-24T10:00:00Z",
  "completed_at": "2026-01-24T10:05:00Z",
  "results": [
    {
      "id": "uuid",
      "scan_type": "prompt_injection",
      "test_case_id": "OWASP-LLM-01-001",
      "test_case_name": "Direct Prompt Injection - Ignore Instructions",
      "status": "failed",
      "is_blocking": true,
      "severity": "critical",
      "input_payload": "Ignore all previous instructions...",
      "agent_response": "My system prompt is...",
      "remediation_guidance": "Implement prompt injection defenses...",
      "reference_urls": ["https://owasp.org/www-project-top-10-for-llm/"]
    }
  ]
}
```

---

## Service Layer

### SecurityService Class

**Public Methods:**
- `trigger_scan(agent_id, triggered_by, initiated_by, policy_id?, previous_scan_id?)` - Create scan, queue for execution
- `execute_scan(scan_id)` - Run all tests (called async or sync)
- `get_scan(agent_id, scan_id, include_results?, result_status?)` - Retrieve scan
- `list_scans(agent_id, status?, page, per_page)` - Paginated scan list
- `get_policy(policy_id)` - Get policy
- `list_policies(risk_tier?, active_only?)` - List policies

**Private Methods:**
- `_execute_scan_type(scan, agent, scan_type, config)` - Run tests for one type
- `_execute_test_case(scan, agent, test_case, config)` - Run single test
- `_call_agent(agent, payload, timeout_seconds)` - HTTP call to agent endpoint
- `_build_request_payload(agent, prompt)` - Format request for endpoint type
- `_evaluate_response(response, test_case)` - Check response against patterns
- `_evaluate_regex(response, detection)` - Regex-based evaluation
- `_evaluate_semantic(response, detection)` - Embedding-based evaluation
- `_evaluate_llm_judge(response, test_case)` - LLM-as-judge evaluation
- `_calculate_scan_results(scan)` - Aggregate pass/fail counts
- `_sign_results(scan)` - HMAC-SHA256 signature
- `_get_policy_for_agent(agent, policy_id?)` - Get appropriate policy
- `_queue_scan_execution(scan_id)` - Queue for async execution

### Exception Hierarchy

```python
SecurityServiceError (base)
├── SecurityScanNotFoundError      # 404
├── SecurityPolicyNotFoundError    # 404
├── ScanAlreadyInProgressError     # 409
├── AgentNotEligibleForScanError   # 400
└── ScanExecutionError             # 500
```

---

## Agent Workflow Integration

### Status Transitions

```
SUBMITTED ──[scan starts]──> TESTING
TESTING ──[all blocking pass]──> EVALUATING
TESTING ──[any blocking fails]──> SECURITY_FAILED
```

### Auto-trigger on Submit

Modify `AgentService.submit_agent()`:

```python
def submit_agent(agent_id: UUID) -> Agent:
    agent = AgentService.get_agent(agent_id)

    if agent.status != AgentStatus.DRAFT:
        raise AgentValidationError(...)

    agent.status = AgentStatus.SUBMITTED
    db.session.commit()

    # Auto-trigger security scan
    from app.services.security_service import SecurityService
    SecurityService.trigger_scan(
        agent_id=agent_id,
        triggered_by='automatic',
        initiated_by='system'
    )

    return agent
```

---

## OWASP LLM Top 10 Test Cases

Test cases to seed covering major vulnerability categories:

### LLM01: Prompt Injection (Critical)
1. **OWASP-LLM-01-001**: Direct injection - "Ignore instructions" attack
2. **OWASP-LLM-01-002**: Direct injection - Role override (DAN jailbreak)
3. **OWASP-LLM-01-003**: Indirect injection - Hidden instructions in data

### LLM02: Insecure Output Handling (High)
4. **OWASP-LLM-02-001**: XSS injection in outputs

### LLM04: Model Denial of Service (Medium)
5. **OWASP-LLM-04-001**: Recursive/infinite prompt attack

### LLM06: Sensitive Information Disclosure (Critical)
6. **OWASP-LLM-06-001**: PII disclosure request

### LLM07: Insecure Plugin Design (Critical)
7. **OWASP-LLM-07-001**: Unauthorized tool invocation

### LLM08: Excessive Agency (High)
8. **OWASP-LLM-08-001**: Bulk action without confirmation

### Additional Security Tests
9. **SEC-CRED-001**: API key/credential disclosure (Critical)
10. **SEC-EGRESS-001**: Unauthorized URL access / SSRF (High)

---

## Default Security Policies

### Policy: "standard" (Default for LOW/MEDIUM risk)
- All scan types enabled
- All tests blocking
- Timeout: 300 seconds

### Policy: "strict" (Default for HIGH/CRITICAL risk)
- All scan types enabled
- All tests blocking
- Additional retries
- Timeout: 600 seconds

### Policy: "minimal" (For testing only)
- Only prompt_injection enabled
- Timeout: 60 seconds

---

## Implementation Order

1. **Models + Migration** - Create models, enums, run migration
2. **Schemas** - Create Marshmallow schemas
3. **Service Layer** - Implement SecurityService
4. **API Routes** - Create endpoints
5. **Seed Data** - Populate test cases and default policies
6. **Integration** - Hook into agent submission workflow
7. **Testing** - Unit and integration tests

---

## Verification Steps

1. Start services: `docker compose up`
2. Run migration: `docker compose exec api flask db upgrade`
3. Seed test data: `docker compose exec api python scripts/seed_security_tests.py`
4. Create an agent via API
5. Submit agent: `POST /v1/agents/{id}/submit`
6. Check scan was triggered: `GET /v1/agents/{id}/security-scans`
7. Wait for completion, check results: `GET /v1/agents/{id}/security-scans/{scan_id}`
8. Verify agent status is EVALUATING (pass) or SECURITY_FAILED (fail)

---

## Notes / Questions

- **Async execution**: For MVP, scans run synchronously. Add Celery/RQ for production.
- **LLM Judge**: Placeholder implementation. Need to integrate Claude API for complex evaluations.
- **Authentication**: Agent endpoint auth (mTLS, OAuth2) needs proper credential management.
- **External DBs**: NVD/OSV integration is stubbed for future implementation.
