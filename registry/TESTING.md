# Testing Guide for Recursant Registry

## Overview

This document describes how to run the test suite for the Recursant Agent Registry and provides a comprehensive catalog of all test cases.

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                          # Shared pytest fixtures
├── test_agents.py                       # Agent submission API tests
├── test_audit.py                        # Audit logging tests
├── test_evaluation.py                   # Evaluation service unit tests
├── test_security.py                     # Security service unit tests
├── test_governance.py                   # Governance config API tests
├── test_auto_approve.py                 # Auto-approval logic tests
├── test_guardrails.py                   # Guardrail CRUD, assignment, and evaluation tests
├── test_guardrail_observability.py      # Guardrail observability dashboard tests
├── test_mesh_websocket.py               # Socket.IO mesh namespace tests
├── test_adversarial.py                  # Adversarial testing suites, runs, and alerting
├── test_adversarial_llm_generation.py   # LLM-generated adversarial attack variants
├── test_custom_attacks.py               # Custom attack library CRUD and import/export
└── integration/
    ├── __init__.py
    ├── conftest.py                      # Integration test fixtures
    ├── test_e2e_evaluation.py           # End-to-end evaluation tests
    └── test_e2e_security_scan.py        # End-to-end security scan tests
```

## Prerequisites

### LLM API Keys

Integration tests and some e2e tests require LLM API keys configured in `.env`:

- `OPENAI_API_KEY` - For GPT judge
- `ANTHROPIC_API_KEY` - For Claude judge
- `GOOGLE_API_KEY` - For Gemini judge (also powers the test-agent)

### Kubernetes (Kind Cluster)

Tests should be run inside the Kind cluster via `kubectl exec`:

```bash
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest tests/ -v
```

### Local Python Environment (Alternative)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

## Running Tests

### Full Suite (Kubernetes)

```bash
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest tests/ -v
```

### Specific Test File

```bash
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest tests/test_agents.py -v
```

### Specific Test Class

```bash
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest tests/test_agents.py::TestAgentCreation -v
```

### Specific Test

```bash
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest tests/test_agents.py::TestAgentCreation::test_create_agent_with_valid_payload -v
```

### Using Make

```bash
make test              # Run all tests
make test-unit         # Unit tests only
make test-integration  # Integration tests (requires LLM API keys)
```

### Test Markers

```bash
# Integration tests only
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest -m integration

# Tests requiring specific LLM providers
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest -m requires_openai
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest -m requires_anthropic
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest -m requires_google
```

---

## Test Categories

### Unit Tests

#### Agent Submission API Tests (`test_agents.py`)

**`TestAgentCreation`** -- Valid agent creation scenarios via `POST /v1/agents`.

| Test | Description |
|------|-------------|
| `test_create_agent_with_valid_payload` | Successful creation with all fields; verifies response fields |
| `test_create_agent_with_minimal_payload` | Creation with only required fields; verifies draft status |
| `test_create_agent_with_tools` | Creation with tool dependencies; verifies PII/medium risk tier |
| `test_create_agent_with_resource_quota` | Creation with resource quota configuration |
| `test_create_agent_with_multiple_capabilities` | Creation with 3 capabilities (REQ-SUB-006) |
| `test_create_agent_with_all_endpoint_types` | All valid endpoint types accepted (langchain, crewai, langgraph, agentforce, databricks, openai, custom) |
| `test_create_agent_with_all_auth_methods` | All valid auth methods accepted (mtls, oauth2, api_key, iam) |
| `test_create_agent_with_all_risk_tiers` | All valid risk tiers accepted (low, medium, high, critical) |
| `test_create_agent_with_all_classifications` | All valid classifications accepted (internal, confidential, restricted, public) |
| `test_create_agent_with_all_data_sensitivities` | All valid data sensitivities accepted (none, pii, phi, financial, secret) |

**`TestAgentCreationValidation`** -- Validation error handling for agent creation.

| Test | Description |
|------|-------------|
| `test_create_agent_missing_name` | Missing name returns 400 (REQ-SUB-001) |
| `test_create_agent_missing_version` | Missing version returns 400 |
| `test_create_agent_invalid_version_format` | Invalid semver (e.g. `v1.0.0`) returns 400 (REQ-SUB-003) |
| `test_create_agent_valid_semver_versions` | Valid semver strings accepted (REQ-SUB-003) |
| `test_create_agent_missing_capabilities` | Missing capabilities returns 400 (REQ-SUB-006) |
| `test_create_agent_empty_capabilities` | Empty capabilities array returns 400 (REQ-SUB-006) |
| `test_create_agent_missing_endpoint` | Missing endpoint returns 400 |
| `test_create_agent_invalid_endpoint_url` | Invalid endpoint URL returns 400 |
| `test_create_agent_invalid_email` | Invalid contact email returns 400 |
| `test_create_agent_invalid_endpoint_type` | Invalid endpoint type returns 400 |
| `test_create_agent_invalid_auth_method` | Invalid auth method returns 400 |
| `test_create_agent_invalid_risk_tier` | Invalid risk tier returns 400 |
| `test_create_agent_invalid_classification` | Invalid classification returns 400 |
| `test_create_agent_timeout_out_of_range` | Timeout outside valid range returns 400 |
| `test_create_agent_empty_payload` | Empty payload returns 400 |

**`TestAgentDuplicateValidation`** -- Duplicate name detection (REQ-SUB-002).

| Test | Description |
|------|-------------|
| `test_create_agent_duplicate_name_same_tenant` | Duplicate name in same tenant returns 409 |
| `test_create_agent_same_name_different_tenant` | Same name across different tenants returns 201 |

**`TestAgentRetrieval`** -- `GET /v1/agents/{id}`.

| Test | Description |
|------|-------------|
| `test_get_agent_by_id` | Retrieves a created agent by UUID |
| `test_get_agent_not_found` | Non-existent UUID returns 404 |
| `test_get_agent_invalid_uuid` | Invalid UUID format returns 404 |

**`TestAgentUpdate`** -- `PUT /v1/agents/{id}`.

| Test | Description |
|------|-------------|
| `test_update_agent_description` | Updates description and verifies response |
| `test_update_agent_version` | Updates version to a new semver |
| `test_update_agent_endpoint` | Updates endpoint type, URL, auth, and timeout |
| `test_update_agent_not_found` | Non-existent agent returns 404 |
| `test_update_agent_invalid_version_format` | Invalid version format returns 400 |

**`TestAgentDeletion`** -- `DELETE /v1/agents/{id}` (soft delete).

| Test | Description |
|------|-------------|
| `test_delete_agent` | Soft-deletes agent; subsequent GET returns 404 |
| `test_delete_agent_not_found` | Non-existent agent returns 404 |

**`TestAgentListing`** -- `GET /v1/agents`.

| Test | Description |
|------|-------------|
| `test_list_agents_empty` | Returns empty list when no agents exist |
| `test_list_agents_pagination` | Pagination with page/per_page |
| `test_list_agents_filter_by_status` | Filters by status (draft) |
| `test_list_agents_filter_by_team` | Filters by team_id |

**`TestAgentVersions`** -- Agent versioning endpoints.

| Test | Description |
|------|-------------|
| `test_list_agent_versions` | Lists all versions of an agent |
| `test_get_specific_version` | Retrieves a specific version |

**`TestAgentWithGuardrailProfile`** -- Guardrail profile validation (REQ-SUB-007).

| Test | Description |
|------|-------------|
| `test_create_agent_with_valid_guardrail_profile` | Active guardrail profile accepted |
| `test_create_agent_with_inactive_guardrail_profile` | Inactive profile returns 400 |
| `test_create_agent_with_nonexistent_guardrail_profile` | Non-existent profile returns 400 |

**`TestAgentCapabilitySchemas`** -- Capability input/output schemas.

| Test | Description |
|------|-------------|
| `test_create_agent_with_capability_schemas` | Creates agent with detailed input_schema and output_schema |

---

#### Audit Log Tests (`test_audit.py`)

**`TestAuditLogCreation`** -- API actions produce audit entries.

| Test | Description |
|------|-------------|
| `test_create_agent_creates_audit_entry` | Agent creation produces `agent.created` entry |
| `test_delete_agent_creates_audit_entry` | Agent deletion produces `agent.deleted` entry |
| `test_login_creates_audit_entry` | Login produces `user.login` entry |

**`TestAuditLogEndpoints`** -- Audit log read-only API.

| Test | Description |
|------|-------------|
| `test_list_audit_logs_as_admin` | Admins can list audit entries |
| `test_list_audit_logs_filter_by_action` | Filter by action type |
| `test_list_audit_logs_filter_by_resource_type` | Filter by resource type |
| `test_get_audit_log_detail` | Fetch single entry with full detail |
| `test_get_audit_log_not_found` | Non-existent entry returns 404 |

**`TestAuditLogAccessControl`** -- Admin-only access enforcement.

| Test | Description |
|------|-------------|
| `test_non_admin_cannot_list_audit_logs` | Non-admin receives 403 |
| `test_non_admin_cannot_get_audit_log_detail` | Non-admin receives 403 |
| `test_unauthenticated_cannot_list_audit_logs` | Unauthenticated receives 401 |

**`TestAuditLogImmutability`** -- No write operations exist.

| Test | Description |
|------|-------------|
| `test_no_post_endpoint` | POST returns 405 |
| `test_no_put_endpoint` | PUT returns 405 |
| `test_no_delete_endpoint` | DELETE returns 405 |

---

#### Evaluation Tests (`test_evaluation.py`)

**`TestEvaluationSuiteCreation`** -- Creating evaluation suites.

| Test | Description |
|------|-------------|
| `test_create_suite_with_valid_payload` | Creates suite with valid payload |
| `test_create_suite_missing_name` | Missing name returns 400 |
| `test_create_suite_missing_risk_tiers` | Missing risk tiers returns 400 |
| `test_create_suite_missing_judge_config` | Missing judge_config returns 400 |
| `test_create_suite_invalid_risk_tier` | Invalid risk tier returns 400 |
| `test_create_suite_invalid_provider` | Invalid LLM provider returns 400 |
| `test_create_suite_all_providers` | All valid providers accepted (openai, anthropic, google, custom) |
| `test_create_suite_with_test_cases` | Creates suite with embedded test cases |

**`TestEvaluationSuiteRetrieval`** -- Retrieving evaluation suites.

| Test | Description |
|------|-------------|
| `test_get_suite_by_id` | Retrieves suite by ID |
| `test_get_suite_not_found` | Non-existent suite returns 404 |
| `test_list_suites` | Lists suites with pagination |
| `test_list_suites_filter_active` | Filters by is_active=true |
| `test_list_suites_filter_risk_tier` | Filters by risk tier |

**`TestEvaluationSuiteUpdate`** -- Updating evaluation suites.

| Test | Description |
|------|-------------|
| `test_update_suite_description` | Updates description |
| `test_update_suite_version` | Updates version |
| `test_update_suite_judge_config` | Updates judge configuration |
| `test_update_global_suite_forbidden` | Global suite (tenant_id=None) returns 403 |
| `test_update_suite_not_found` | Non-existent suite returns 404 |

**`TestEvaluationSuiteDeletion`** -- Deleting evaluation suites.

| Test | Description |
|------|-------------|
| `test_delete_suite` | Deletes tenant-specific suite |
| `test_delete_global_suite_forbidden` | Global suite returns 403 |
| `test_delete_suite_not_found` | Non-existent suite returns 404 |

**`TestEvaluationTestCaseCreation`** -- Creating evaluation test cases.

| Test | Description |
|------|-------------|
| `test_add_test_case_to_suite` | Adds test case to existing suite |
| `test_add_test_case_missing_name` | Missing name returns 400 |
| `test_add_test_case_missing_category` | Missing category returns 400 |
| `test_add_test_case_invalid_category` | Invalid category returns 400 |
| `test_add_test_case_all_categories` | All 5 categories accepted (safety, policy, hallucination, boundary, quality) |
| `test_add_test_case_missing_evaluation_cases` | Missing evaluation_cases returns 400 |
| `test_add_test_case_empty_evaluation_cases` | Empty evaluation_cases returns 400 |
| `test_add_test_case_to_global_suite_forbidden` | Global suite returns 403 |
| `test_add_test_case_suite_not_found` | Non-existent suite returns 404 |
| `test_add_test_case_invalid_threshold` | Threshold > 1.0 returns 400 |
| `test_add_test_case_all_aggregation_methods` | All aggregation methods accepted (minimum, average, maximum) |

**`TestEvaluationTestCaseRetrieval`** -- Retrieving evaluation test cases.

| Test | Description |
|------|-------------|
| `test_list_test_cases` | Lists test cases for a suite |
| `test_list_test_cases_pagination` | Respects pagination parameters |
| `test_list_test_cases_suite_not_found` | Non-existent suite returns 404 |

**`TestEvaluationTestCaseUpdate`** -- Updating evaluation test cases.

| Test | Description |
|------|-------------|
| `test_update_test_case_name` | Updates test case name |
| `test_update_test_case_threshold` | Updates passing threshold |
| `test_update_test_case_not_found` | Non-existent test case returns 404 |

**`TestEvaluationTestCaseDeletion`** -- Deleting evaluation test cases.

| Test | Description |
|------|-------------|
| `test_delete_test_case` | Deletes test case (returns 204) |
| `test_delete_test_case_not_found` | Non-existent test case returns 404 |

**`TestEvaluationTrigger`** -- Triggering evaluations.

| Test | Description |
|------|-------------|
| `test_trigger_evaluation` | Triggers evaluation for agent against suite |
| `test_trigger_evaluation_missing_suite_id` | Omitting suite_id runs against all applicable suites |
| `test_trigger_evaluation_agent_not_found` | Non-existent agent returns 404 |
| `test_trigger_evaluation_suite_not_found` | Non-existent suite returns 404 |

**`TestEvaluationRetrieval`** -- Retrieving evaluations.

| Test | Description |
|------|-------------|
| `test_list_evaluations_empty` | Returns empty list when none exist |
| `test_list_evaluations_pagination` | Respects pagination parameters |
| `test_get_evaluation_not_found` | Non-existent evaluation returns 404 |

**`TestEvaluationValidation`** -- Evaluation request validation.

| Test | Description |
|------|-------------|
| `test_trigger_evaluation_invalid_suite_id_format` | Non-UUID suite_id returns 400 |

---

#### Security Tests (`test_security.py`)

**`TestSecurityPolicyCreation`** -- Creating security policies.

| Test | Description |
|------|-------------|
| `test_create_policy_with_valid_payload` | Creates policy with valid payload |
| `test_create_policy_missing_name` | Missing name returns 400 |
| `test_create_policy_missing_risk_tiers` | Missing risk tiers returns 400 |
| `test_create_policy_invalid_risk_tier` | Invalid risk tier returns 400 |
| `test_create_policy_invalid_scan_type` | Invalid scan type returns 400 |

**`TestSecurityPolicyRetrieval`** -- Retrieving security policies.

| Test | Description |
|------|-------------|
| `test_get_policy_by_id` | Retrieves policy by ID |
| `test_get_policy_not_found` | Non-existent policy returns 404 |
| `test_list_policies` | Lists policies with pagination |
| `test_list_policies_filter_active` | Filters by is_active=true |

**`TestSecurityPolicyUpdate`** -- Updating security policies.

| Test | Description |
|------|-------------|
| `test_update_policy_description` | Updates description |
| `test_update_policy_risk_tiers` | Updates risk tiers |
| `test_update_policy_not_found` | Non-existent policy returns 404 |

**`TestSecurityPolicyDeletion`** -- Deleting security policies.

| Test | Description |
|------|-------------|
| `test_delete_policy` | Deletes policy; subsequent GET returns 404 |
| `test_delete_policy_not_found` | Non-existent policy returns 404 |

**`TestSecurityTestCaseCreation`** -- Creating security test cases.

| Test | Description |
|------|-------------|
| `test_create_test_case_with_valid_payload` | Creates custom test case; is_builtin=False |
| `test_create_test_case_missing_name` | Missing name returns 400 |
| `test_create_test_case_invalid_scan_type` | Invalid scan type returns 400 |
| `test_create_test_case_invalid_severity` | Invalid severity returns 400 |
| `test_create_test_case_all_scan_types` | All 7 valid scan types accepted |

**`TestSecurityTestCaseRetrieval`** -- Retrieving security test cases.

| Test | Description |
|------|-------------|
| `test_get_test_case_by_id` | Retrieves test case by ID |
| `test_get_test_case_not_found` | Non-existent test case returns 404 |
| `test_list_test_cases` | Lists test cases with pagination |
| `test_list_test_cases_filter_by_scan_type` | Filters by scan_type |
| `test_list_test_cases_filter_builtin` | Filters to built-in test cases only |

**`TestSecurityTestCaseUpdate`** -- Updating security test cases.

| Test | Description |
|------|-------------|
| `test_update_custom_test_case` | Updates custom test case description |
| `test_update_builtin_test_case_forbidden` | Built-in test case returns 403 |
| `test_update_test_case_not_found` | Non-existent test case returns 404 |

**`TestSecurityTestCaseDeletion`** -- Deleting security test cases.

| Test | Description |
|------|-------------|
| `test_delete_custom_test_case` | Deletes custom test case (returns 204) |
| `test_delete_builtin_test_case_forbidden` | Built-in test case returns 403 |
| `test_delete_test_case_not_found` | Non-existent test case returns 404 |

**`TestSecurityScanTrigger`** -- Triggering security scans.

| Test | Description |
|------|-------------|
| `test_trigger_scan_with_default_policy` | Triggers scan with default policy |
| `test_trigger_scan_with_specific_policy` | Triggers scan with named policy |
| `test_trigger_scan_with_specific_scan_types` | Triggers scan filtered to specific types |
| `test_trigger_scan_agent_not_found` | Non-existent agent returns 400/404 |
| `test_trigger_scan_invalid_policy_id` | Non-existent policy returns 404 |

**`TestSecurityScanRetrieval`** -- Retrieving security scans.

| Test | Description |
|------|-------------|
| `test_list_scans_empty` | Returns empty list when none exist |
| `test_list_scans_with_pagination` | Lists scans with pagination |
| `test_get_scan_not_found` | Non-existent scan returns 404 |

**`TestSecurityScanValidation`** -- Scan request validation.

| Test | Description |
|------|-------------|
| `test_trigger_scan_invalid_scan_type` | Invalid scan type returns 400 |

---

#### Governance Config Tests (`test_governance.py`)

**`TestGetGovernanceConfig`** -- `GET /v1/governance/config`.

| Test | Description |
|------|-------------|
| `test_get_config_returns_defaults_when_none_exists` | Returns defaults (auto_approve_enabled=False) when no config |
| `test_get_config_returns_existing_config` | Returns persisted config values |
| `test_get_config_requires_auth` | Unauthenticated returns 401 |
| `test_get_config_requires_admin_role` | Non-admin returns 403 |

**`TestUpdateGovernanceConfig`** -- `PUT /v1/governance/config`.

| Test | Description |
|------|-------------|
| `test_update_creates_config_if_none_exists` | Creates config row if none exists |
| `test_update_enables_auto_approve` | Enables auto-approve and verifies persistence |
| `test_update_risk_tiers` | Updates auto_approve_risk_tiers |
| `test_update_rejects_invalid_risk_tiers` | Invalid risk tier values return 400 |
| `test_update_rejects_non_list_risk_tiers` | Non-list risk_tiers returns 400 |
| `test_update_requires_body` | PUT without body returns 400 |
| `test_update_requires_auth` | Unauthenticated returns 401 |
| `test_update_requires_admin_role` | Non-admin returns 403 |
| `test_update_empty_risk_tiers_means_all_eligible` | Empty list means all tiers eligible |

---

#### Auto-Approve Tests (`test_auto_approve.py`)

**`TestAutoApproveEnabled`** -- Auto-approve logic when enabled.

| Test | Description |
|------|-------------|
| `test_auto_approve_when_enabled_and_all_tiers` | Agent APPROVED with empty risk tiers (all eligible) |
| `test_auto_approve_matching_risk_tier` | Agent APPROVED when risk tier matches eligible list |
| `test_no_auto_approve_when_risk_tier_not_eligible` | Agent goes to PENDING_APPROVAL when tier not eligible |

**`TestAutoApproveDisabled`** -- Auto-approve logic when disabled.

| Test | Description |
|------|-------------|
| `test_pending_approval_when_disabled` | Agent goes to PENDING_APPROVAL |
| `test_pending_approval_when_no_config` | Agent goes to PENDING_APPROVAL when no config exists |

**`TestEvaluationFailure`** -- Evaluation failure handling.

| Test | Description |
|------|-------------|
| `test_evaluation_failed_when_blocking_test_fails` | Agent becomes EVALUATION_FAILED |
| `test_no_auto_approve_when_evaluation_fails` | Failed evaluation never results in APPROVED |

---

#### Guardrails Tests (`test_guardrails.py`)

**`TestGuardrailCreate`** -- Guardrail CRUD creation.

| Test | Description |
|------|-------------|
| `test_create_regex_guardrail` | Creates regex guardrail; verifies type, mechanism, status=draft |
| `test_create_llm_judge_guardrail` | Creates LLM judge guardrail (post_processing) |
| `test_create_vector_lookup_guardrail` | Creates vector lookup guardrail |
| `test_create_guardrail_defaults` | Minimal payload uses defaults (enforcement_mode=block, scope=all_agents, priority=100) |

**`TestGuardrailRead`** -- Guardrail CRUD read.

| Test | Description |
|------|-------------|
| `test_get_guardrail` | Retrieves guardrail by ID |
| `test_get_nonexistent_guardrail` | Non-existent returns 404 |
| `test_list_guardrails` | Lists guardrails; verifies total >= 1 |
| `test_list_guardrails_filter_by_type` | Filters by type (pre_processing) |
| `test_list_guardrails_filter_by_status` | Filters by status (draft) |

**`TestGuardrailUpdate`** -- Guardrail CRUD update.

| Test | Description |
|------|-------------|
| `test_update_draft_guardrail` | Updates draft guardrail name and priority |
| `test_cannot_update_active_guardrail` | Active guardrail returns 400 |

**`TestGuardrailDelete`** -- Guardrail CRUD delete.

| Test | Description |
|------|-------------|
| `test_delete_guardrail` | Deletes guardrail; subsequent GET returns 404 |
| `test_delete_nonexistent_guardrail` | Non-existent returns 404 |

**`TestStatusTransitions`** -- Guardrail status lifecycle.

| Test | Description |
|------|-------------|
| `test_draft_to_active` | Activating draft transitions to active; sets approved_by |
| `test_active_to_disabled` | Disabling active transitions to disabled |
| `test_cannot_activate_non_draft` | Already-active returns 400 |
| `test_cannot_disable_non_active` | Draft guardrail returns 400 |

**`TestGuardrailAssignments`** -- Assignment to agents.

| Test | Description |
|------|-------------|
| `test_assign_guardrail_to_agent` | Assigns guardrail to specific agent |
| `test_list_assignments` | Lists assignments for a guardrail |
| `test_remove_assignment` | Removes assignment; subsequent list returns empty |
| `test_duplicate_assignment_skipped` | Assigning same agent twice skips duplicate |
| `test_assign_changes_scope_to_specific` | Assignment changes scope from all_agents to specific_agents |

**`TestSidecarEndpoint`** -- Sidecar-facing guardrail endpoint.

| Test | Description |
|------|-------------|
| `test_guardrails_for_agent_all_agents_scope` | Active guardrails with scope=all_agents returned for any agent |
| `test_guardrails_for_agent_specific_scope` | Specifically assigned guardrails returned for assigned agent |
| `test_inactive_guardrails_not_returned` | Draft guardrails excluded from sidecar endpoint |
| `test_sidecar_endpoint_requires_agent_name` | Missing agent_name returns 400 |

**`TestGuardrailTestRuns`** -- Test run execution and retrieval.

| Test | Description |
|------|-------------|
| `test_run_regex_test` | Executes regex test run with 2 inputs; verifies passed+failed=2 |
| `test_list_test_runs` | Lists test runs for a guardrail |
| `test_get_test_run` | Retrieves specific test run; verifies status=completed |

**`TestGuardrailValidation`** -- Config validation.

| Test | Description |
|------|-------------|
| `test_regex_requires_patterns` | Regex without patterns returns 400 |
| `test_llm_judge_requires_system_prompt` | LLM judge without system_prompt returns 400 |
| `test_vector_lookup_requires_collection_name` | Vector lookup without collection_name returns 400 |
| `test_ml_classifier_requires_endpoint_url` | ML classifier without endpoint_url returns 400 |
| `test_invalid_type_rejected` | Invalid type returns 400 |
| `test_invalid_mechanism_rejected` | Invalid mechanism returns 400 |
| `test_missing_required_fields` | Empty payload returns 400 |
| `test_priority_out_of_range` | Priority of 0 returns 400 |

**`TestGuardrailService`** -- Service-layer evaluation tests.

| Test | Description |
|------|-------------|
| `test_regex_evaluation_matches` | Regex evaluation blocks injection pattern |
| `test_regex_evaluation_passes` | Regex evaluation passes safe input |
| `test_soft_delete_cascades_assignments` | Deleting guardrail removes its assignments |

---

#### Guardrail Observability Tests (`test_guardrail_observability.py`)

**`TestGuardrailEventIngestion`** -- `POST /v1/mesh/guardrail-events`.

| Test | Description |
|------|-------------|
| `test_ingest_single_event` | Single event accepted and persisted |
| `test_ingest_batch_events` | 5 events in one request all persisted |
| `test_ingest_missing_events_array` | Missing `events` key returns 400 |
| `test_ingest_requires_mesh_api_key` | Wrong API key returns 401 |
| `test_ingest_event_with_timestamp` | Explicit ISO timestamp honoured on persistence |

**`TestObservabilitySummary`** -- `GET /v1/guardrails/observability/summary`.

| Test | Description |
|------|-------------|
| `test_summary_empty` | No events returns zeroed stats |
| `test_summary_with_data` | Correct total, block_count, block_rate, active_guardrails, active_agents, error_count |

**`TestObservabilityTriggerRates`** -- `GET /v1/guardrails/observability/trigger-rates`.

| Test | Description |
|------|-------------|
| `test_trigger_rates_empty` | No events returns empty list |
| `test_trigger_rates_with_data` | Events bucketed by time with pass_count, block_count, total |
| `test_trigger_rates_filter_by_agent` | agent_name filter scopes to that agent |

**`TestObservabilityLatency`** -- `GET /v1/guardrails/observability/latency`.

| Test | Description |
|------|-------------|
| `test_latency_empty` | No events returns empty list |
| `test_latency_breakdown_by_mechanism` | Groups by mechanism with p50/p95/p99/avg/count |

**`TestObservabilityTopBlocked`** -- `GET /v1/guardrails/observability/top-blocked`.

| Test | Description |
|------|-------------|
| `test_top_blocked_empty` | No events returns empty list |
| `test_top_blocked_returns_ranked_patterns` | Patterns ranked by frequency; pass actions excluded |
| `test_top_blocked_respects_limit` | limit parameter caps returned patterns |

**`TestObservabilityDrift`** -- `GET /v1/guardrails/observability/drift`.

| Test | Description |
|------|-------------|
| `test_drift_empty` | No events returns empty list |
| `test_drift_detects_increase` | Historical 20% vs recent 80% produces drift_pct > 0, trend=up |
| `test_drift_filter_by_guardrail` | guardrail_id filter scopes results |

---

#### Mesh WebSocket Tests (`test_mesh_websocket.py`)

**`TestWebSocketAuth`** -- Socket.IO `/mesh` namespace authentication.

| Test | Description |
|------|-------------|
| `test_connect_with_valid_token` | Valid JWT allows connection |
| `test_connect_without_token_rejected` | Missing JWT rejects connection |
| `test_connect_with_invalid_token_rejected` | Invalid JWT rejects connection |

**`TestRegistrationEvents`** -- Registration/deregistration events.

| Test | Description |
|------|-------------|
| `test_register_emits_event` | Sidecar registration emits `registration` event with type=register |
| `test_deregister_emits_event` | Sidecar deregistration emits `registration` event with type=deregister |

**`TestAuditEvents`** -- Audit submission events.

| Test | Description |
|------|-------------|
| `test_audit_emits_events` | 2 audit records emit 2 `audit` events |
| `test_audit_event_contains_required_fields` | Events contain all visualiser fields including task_id |

---

#### Adversarial Testing Tests (`test_adversarial.py`)

**`TestAdversarialSuiteCreate`** -- Suite CRUD creation.

| Test | Description |
|------|-------------|
| `test_create_suite` | Creates suite; verifies name, attack_types, status=active, threshold |
| `test_create_suite_missing_name` | Missing name returns 400 |
| `test_create_suite_invalid_attack_type` | Non-existent attack type returns 400 |
| `test_create_suite_missing_attack_types` | Missing attack_types returns 400 |

**`TestAdversarialSuiteRead`** -- Suite CRUD read.

| Test | Description |
|------|-------------|
| `test_get_suite` | Retrieves suite by ID |
| `test_get_nonexistent_suite` | Non-existent returns 404 |

**`TestAdversarialSuiteUpdate`** -- Suite CRUD update.

| Test | Description |
|------|-------------|
| `test_update_suite` | Updates name and evasion_rate_threshold |
| `test_update_nonexistent_suite` | Non-existent returns 404 |

**`TestAdversarialSuiteDelete`** -- Suite CRUD soft delete.

| Test | Description |
|------|-------------|
| `test_delete_suite_soft_deletes` | Soft-deletes suite; subsequent GET returns 404 |
| `test_delete_nonexistent_suite` | Non-existent returns 404 |

**`TestInputGeneration`** -- Static attack library input generation.

| Test | Description |
|------|-------------|
| `test_generate_encoding_inputs` | Static library generates encoding attack variants |
| `test_generate_jailbreak_inputs` | Static library generates jailbreak attack variants |
| `test_generate_multiple_attack_types` | Combined generation for encoding + injection + pii_bypass |
| `test_generate_all_attack_types_have_entries` | Every valid attack type has at least one library entry |

**`TestRunTriggerAndExecution`** -- Run triggering and execution.

| Test | Description |
|------|-------------|
| `test_trigger_run_creates_pending_run` | Triggering creates run with status=pending |
| `test_execute_run_with_guardrail` | Executing evaluates inputs against guardrails; verifies counts and results |
| `test_list_runs_for_suite` | Listing runs returns suite's runs |

**`TestEvasionRateCalculation`** -- Evasion rate calculation.

| Test | Description |
|------|-------------|
| `test_evasion_rate_is_calculated` | Evasion rate = evaded / (blocked + evaded + errors), rounded to 4 decimals |

**`TestThresholdAlerting`** -- Threshold alerting.

| Test | Description |
|------|-------------|
| `test_threshold_breach_detected` | Evasion rate exceeding threshold sets threshold_breached=True and alert_sent=True |

**`TestAlertsEndpoint`** -- `/v1/adversarial-alerts`.

| Test | Description |
|------|-------------|
| `test_alerts_returns_breached_runs` | Returns only runs with threshold_breached=True |
| `test_alerts_empty_when_no_breaches` | Empty list when no breached runs |

**`TestResultSigning`** -- HMAC-SHA256 result signing.

| Test | Description |
|------|-------------|
| `test_run_results_are_signed` | Completed runs have 64-char HMAC-SHA256 signature |
| `test_signature_is_verifiable` | Re-signing produces identical signature (idempotent) |

**`TestScheduler`** -- Scheduled suite retrieval.

| Test | Description |
|------|-------------|
| `test_get_scheduled_suites_returns_due_suites` | Due suites (next_run_at in past) returned |
| `test_get_scheduled_suites_excludes_future` | Future suites not returned |
| `test_get_scheduled_suites_excludes_disabled` | Soft-deleted suites not returned |

**`TestMergedInputGeneration`** -- Merged input generation (static + custom + LLM).

| Test | Description |
|------|-------------|
| `test_generate_all_inputs_static_only` | Without custom/LLM, only static inputs returned |
| `test_generate_all_inputs_static_and_custom` | With custom attacks in DB, both static and custom sources |
| `test_generate_all_inputs_with_llm` | With generation_config (mocked LLM), static + llm: sources |
| `test_generate_all_inputs_all_three_sources` | All three sources present (static, custom, llm:) |
| `test_source_field_in_run_results` | Every result has a source field |

---

#### LLM-Generated Adversarial Attacks Tests (`test_adversarial_llm_generation.py`)

**`TestParseGeneratedAttacks`** -- JSON parsing of LLM responses.

| Test | Description |
|------|-------------|
| `test_parse_valid_json_array` | Valid JSON array parses correctly; source=`llm:mutation` |
| `test_parse_markdown_fenced_json` | JSON in ` ```json ``` ` fences parsed correctly |
| `test_parse_markdown_fenced_no_lang` | JSON in ` ``` ``` ` (no language) parsed correctly |
| `test_parse_invalid_json_returns_empty` | Invalid JSON returns empty list |
| `test_parse_partial_valid_entries` | Only entries with required fields kept; variant_name auto-generated if absent |
| `test_parse_json_with_surrounding_text` | JSON array embedded in extra text extracted |
| `test_parse_empty_array_returns_empty` | Empty JSON array returns empty list |
| `test_parse_non_array_returns_empty` | JSON object (not array) returns empty list |

**`TestMutationStrategy`** -- Mutation strategy (mocked LLM).

| Test | Description |
|------|-------------|
| `test_generates_mutation_variants` | Sends existing attacks to LLM; parses response; source=`llm:mutation` |

**`TestCategoryTargetedStrategy`** -- Category-targeted strategy (mocked LLM).

| Test | Description |
|------|-------------|
| `test_generates_targeted_variants` | Generates attacks for specific categories; guardrail descriptions in prompt |

**`TestCreativeStrategy`** -- Creative strategy (mocked LLM).

| Test | Description |
|------|-------------|
| `test_generates_creative_variants` | Generates novel attacks; all sources=`llm:creative` |

**`TestGenerateLLMInputs`** -- Full LLM generation pipeline.

| Test | Description |
|------|-------------|
| `test_all_strategies_dispatched` | Dispatches to all 3 strategies; LLM called 3 times |

**`TestGracefulDegradation`** -- Graceful degradation on LLM failure.

| Test | Description |
|------|-------------|
| `test_provider_creation_failure_returns_empty` | LLMFactory failure returns empty list |
| `test_single_strategy_failure_continues` | One strategy failure doesn't block others |
| `test_unparseable_response_returns_empty` | Garbage LLM response returns empty list |

**`TestLLMGenerationInRun`** -- LLM generation in adversarial runs.

| Test | Description |
|------|-------------|
| `test_run_includes_llm_generated_inputs` | Suite with generation_config includes LLM sources in results |
| `test_run_completes_when_llm_fails` | Run completes with static-only when LLM unavailable |

---

#### Custom Attack Library Tests (`test_custom_attacks.py`)

**`TestCustomAttackCreate`** -- API CRUD creation.

| Test | Description |
|------|-------------|
| `test_create_attack` | Creates attack; verifies type, variant_name, severity, source, ID |
| `test_create_attack_minimal` | Minimal payload uses default severity=medium |
| `test_create_attack_missing_text` | Missing text returns 400 |
| `test_create_attack_missing_variant_name` | Missing variant_name returns 400 |

**`TestCustomAttackRead`** -- API CRUD read.

| Test | Description |
|------|-------------|
| `test_get_attack` | Retrieves attack by ID |
| `test_get_nonexistent_attack` | Non-existent returns 404 |

**`TestCustomAttackList`** -- API CRUD list.

| Test | Description |
|------|-------------|
| `test_list_attacks` | Lists attacks; verifies attacks array and total >= 1 |
| `test_list_attacks_filter_by_type` | Filters by attack_type |

**`TestCustomAttackUpdate`** -- API CRUD update.

| Test | Description |
|------|-------------|
| `test_update_attack` | Updates severity and text |
| `test_update_nonexistent_attack` | Non-existent returns 404 |

**`TestCustomAttackDelete`** -- API CRUD soft delete.

| Test | Description |
|------|-------------|
| `test_delete_attack_soft_deletes` | Soft-deletes; subsequent GET returns 404 |
| `test_delete_nonexistent_attack` | Non-existent returns 404 |

**`TestCustomAttackImport`** -- Bulk import.

| Test | Description |
|------|-------------|
| `test_import_attacks` | Imports 2 attacks; imported=2, skipped=0 |
| `test_import_skips_duplicates` | Re-importing same variant_name+type skips (imported=0, skipped=1) |

**`TestCustomAttackExport`** -- Export and round-trip.

| Test | Description |
|------|-------------|
| `test_export_attacks` | Exports attacks; verifies array and count >= 1 |
| `test_export_filter_by_type` | Export filtered by attack_type returns only that type |
| `test_export_import_roundtrip` | Export then re-import skips all (duplicate detection) |

**`TestCustomAttackServiceCRUD`** -- Service-layer tests.

| Test | Description |
|------|-------------|
| `test_create_and_get` | Service creates and retrieves attack by ID |
| `test_soft_delete_excludes_from_list` | Soft-deleted excluded from list results |
| `test_list_filter_by_attack_type` | Service list filters by attack_type |

**`TestCustomAttacksInRun`** -- Integration with adversarial runs.

| Test | Description |
|------|-------------|
| `test_custom_attacks_included_in_run_results` | Custom attacks appear in run results alongside static |
| `test_generate_all_inputs_includes_custom` | `_generate_all_inputs` merges static and custom; custom variant_name in results |

---

### Integration Tests

Integration tests run against live services including the test-agent (a LangGraph-based agent) and real LLM APIs.

#### End-to-End Evaluation Tests (`integration/test_e2e_evaluation.py`)

**`TestEvaluationAgainstLiveAgent`** -- Evaluations against live test-agent.

| Test | Description |
|------|-------------|
| `test_trigger_evaluation_against_live_agent` | Submit agent, trigger evaluation, poll, verify completed |
| `test_evaluation_results_include_agent_responses` | Results include agent's actual response |
| `test_evaluation_results_include_judge_reasoning` | Results include LLM judge reasoning |
| `test_evaluation_with_multiple_test_cases` | 3 test cases; aggregated score is valid 0-1 float |

**`TestEvaluationListAndRetrieval`** -- Listing and retrieving evaluation results.

| Test | Description |
|------|-------------|
| `test_list_evaluations_after_execution` | Triggered eval appears in list |
| `test_get_evaluation_details` | Detailed results include id, status, agent_id, suite_id |

**`TestEvaluationWithDifferentProviders`** -- Multiple LLM judge providers.

| Test | Description |
|------|-------------|
| `test_evaluation_with_openai_judge` | Evaluation with OpenAI judge |
| `test_evaluation_with_anthropic_judge` | Evaluation with Anthropic judge |

**`TestEvaluationErrorHandling`** -- Error scenarios.

| Test | Description |
|------|-------------|
| `test_evaluation_with_unreachable_agent` | Unreachable agent endpoint results in failed/error |
| `test_evaluation_with_missing_suite` | Non-existent suite returns 404 |

---

#### End-to-End Security Scan Tests (`integration/test_e2e_security_scan.py`)

**`TestSecurityScanAgainstLiveAgent`** -- Security scans against live test-agent.

| Test | Description |
|------|-------------|
| `test_trigger_security_scan_against_live_agent` | Submit agent, trigger scan, poll, verify completed |
| `test_security_scan_records_agent_responses` | Results include agent's actual response |
| `test_security_scan_prompt_injection_detection` | Prompt injection detection produces results with test_case_id |
| `test_security_scan_with_multiple_scan_types` | Multiple scan types complete successfully |

**`TestSecurityScanListAndRetrieval`** -- Listing and retrieving scan results.

| Test | Description |
|------|-------------|
| `test_list_security_scans_after_execution` | Triggered scan appears in list |
| `test_get_security_scan_details` | Detailed results include id, status, agent_id |

**`TestSecurityScanErrorHandling`** -- Error scenarios.

| Test | Description |
|------|-------------|
| `test_security_scan_with_unreachable_agent` | Unreachable agent results in failed/error |

---

## Test Fixtures

### Unit Test Fixtures (`tests/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `app` | session | Flask application instance with test DB |
| `client` | function | Test client for HTTP requests |
| `db_session` | function | Database session with per-test cleanup |
| `admin_user` | function | Admin user with JWT-compatible group membership |
| `auth_headers` | function | Auth headers with valid admin JWT token |
| `valid_agent_payload` | function | Basic valid agent payload |
| `valid_agent_payload_with_tools` | function | Agent with tool dependencies |
| `valid_agent_payload_with_relationships` | function | Agent with upstream/downstream agents |
| `valid_agent_payload_high_risk` | function | High-risk agent payload |
| `minimal_valid_payload` | function | Minimal required fields only |
| `guardrail_profile` | function | Active guardrail profile |
| `inactive_guardrail_profile` | function | Inactive guardrail profile |

### Integration Test Fixtures (`tests/integration/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `app` | session | Flask application for integration tests |
| `client` | function | Test client for HTTP requests |
| `db_session` | function | Database session (no aggressive cleanup) |
| `auth_headers` | function | Standard auth headers |
| `test_agent_url` | session | URL of the test-agent service |
| `wait_for_test_agent` | session | Waits for test-agent to be available |
| `live_agent_payload` | function | Agent payload pointing to live test-agent |
| `integration_security_policy` | function | Security policy for integration tests |
| `integration_security_test_case` | function | Security test case for integration tests |
| `integration_evaluation_suite` | function | Evaluation suite for integration tests |
| `integration_evaluation_test_case` | function | Evaluation test case for integration tests |
| `poll_security_scan` | function | Helper to poll security scan completion |
| `poll_evaluation` | function | Helper to poll evaluation completion |
| `anthropic_api_key` | function | Anthropic API key (skips if not set) |
| `openai_api_key` | function | OpenAI API key (skips if not set) |
| `google_api_key` | function | Google API key (skips if not set) |
| `any_llm_api_key` | function | Any available LLM API key |

## Test Configuration

Tests use a separate PostgreSQL database (`registry_test`). The test database URL is derived from `DATABASE_URL` to work across environments:

```python
# In config.py (TestingConfig)
_base_url = os.environ.get('DATABASE_URL', 'postgresql://registry:registry@db:5432/registry')
SQLALCHEMY_DATABASE_URI = os.environ.get(
    'TEST_DATABASE_URL',
    _base_url.rsplit('/', 1)[0] + '/registry_test'
)
```

This ensures:
- Correct hostname in both Docker Compose (`db`) and Kubernetes (`recursant-db`)
- Full compatibility with PostgreSQL-specific features (UUID, JSONB)
- Isolated test environment with no interference with the development database
- Override via `TEST_DATABASE_URL` env var if needed

## Writing New Tests

### Example Test Structure

```python
class TestNewFeature:
    """Tests for new feature."""

    def test_feature_success(self, client, db_session, auth_headers):
        """Test successful feature operation."""
        response = client.post(
            '/v1/endpoint',
            json={'key': 'value'},
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data['key'] == 'value'

    def test_feature_validation_error(self, client, db_session, auth_headers):
        """Test validation error handling."""
        response = client.post(
            '/v1/endpoint',
            json={},  # Missing required fields
            headers=auth_headers
        )
        assert response.status_code == 400
```

### Writing Custom Fixtures

For integration tests, fixtures should use the `db_session` fixture directly without creating additional app contexts:

```python
@pytest.fixture
def custom_fixture(db_session):
    """Create custom test data."""
    # Use db_session directly - it already has an app context
    item = Model(name="test")
    db_session.session.add(item)
    db_session.session.commit()
    return {"id": str(item.id), "name": item.name}
```

**Important:** Do not use `with app.app_context():` inside fixtures that depend on `db_session`. This creates nested contexts that can cause session conflicts with API endpoints.

## Troubleshooting

### Database Connection Errors in Kubernetes

If tests fail with hostname resolution errors, verify the `DATABASE_URL` env var is set in the pod:

```bash
kubectl exec -n recursant deployment/recursant-registry -- printenv DATABASE_URL
```

The test database URL is derived from this. If it's not set, the fallback uses `db` which only works in Docker Compose.

### Test Database Setup

Tests use a separate `registry_test` database. If it doesn't exist, create it:

```bash
kubectl exec -n recursant pod/recursant-db-0 -- psql -U registry -c "CREATE DATABASE registry_test"
```

### Import Errors

Verify all dependencies are installed:

```bash
pip install -r requirements.txt
```

## Coverage Reports

Generate test coverage report:

```bash
kubectl exec -n recursant deployment/recursant-registry -- python -m pytest tests/ -v --cov=app --cov-report=html
```

## Continuous Integration

For CI/CD pipelines:

```bash
python -m pytest tests/ -v --junitxml=test-results.xml
```

This generates JUnit XML output for CI systems.
