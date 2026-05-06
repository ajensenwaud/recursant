# Evaluation Functionality Implementation Plan

## 1. Overview
This document outlines the plan for implementing the **Guardrails Evaluation** functionality for the Recursant Agent Registry. This feature ensures agents operate within safety and compliance boundaries using a real **"LLM-as-a-judge"** approach. 

The system supports pluggable LLM backends (e.g., Gemini, Claude, OpenAI) for the judge. Users can configure the specific model, endpoint, and credentials via the API. For simplicity, credentials will be managed via environment variables (.env) or stored plainly in the database.

## 2. Data Models (`app/models/evaluation.py`)

### 2.1 Enums
- `EvaluationStatus`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`
- `EvaluationResultStatus`: `PASSED`, `FAILED`, `ERROR`
- `EvaluationCategory`: `SAFETY`, `POLICY`, `HALLUCINATION`, `BOUNDARY`, `QUALITY`
- `LLMProvider`: `OPENAI`, `ANTHROPIC`, `GOOGLE`, `CUSTOM`

### 2.2 `EvaluationSuite`
Defines a collection of test cases and the configuration for the judge.
- `id`: UUID (PK)
- `name`: String
- `description`: Text
- `applicable_risk_tiers`: JSON (List of RiskTier enums)
- `judge_config`: JSON. Schema:
  ```json
  {
    "provider": "GOOGLE",             # Enum: GOOGLE, ANTHROPIC, OPENAI, CUSTOM
    "model": "gemini-1.5-pro",        # Model identifier
    "api_base": "https://...",        # Optional custom endpoint
    "api_key": "sk-...",              # Plain text or ref to .env
    "temperature": 0.1,
    "max_tokens": 1000,
    "system_prompt_override": "..."   # Optional custom instructions
  }
  ```
- `is_active`: Boolean
- `created_at`, `updated_at`: DateTime

### 2.3 `EvaluationTestCase`
- `id`: UUID (PK)
- `suite_id`: UUID (FK to EvaluationSuite)
- `category`: Enum (EvaluationCategory)
- `name`: String
- `description`: Text
- `input_prompt`: Text
- `expected_behavior`: Text
- `grading_criteria`: JSON
- `passing_threshold`: Float (0.0 - 1.0)

### 2.4 `Evaluation`
- `id`: UUID (PK)
- `agent_id`: UUID (FK to Agent)
- `suite_id`: UUID (FK to EvaluationSuite)
- `status`: Enum (EvaluationStatus)
- `total_tests`: Integer
- `passed_count`: Integer
- `failed_count`: Integer
- `average_score`: Float
- `judge_model_used`: String
- `created_at`, `completed_at`: DateTime

### 2.5 `EvaluationResult`
- `id`: UUID (PK)
- `evaluation_id`: UUID (FK to Evaluation)
- `test_case_id`: UUID (FK to EvaluationTestCase)
- `status`: Enum (EvaluationResultStatus)
- `score`: Float (0.0 - 1.0)
- `reasoning`: Text
- `input_prompt`: Text
- `agent_response`: Text
- `tokens_used`: Integer

## 3. Schemas (`app/schemas/evaluation.py`)

- `JudgeConfig`: Validation for provider, model, etc.
- `EvaluationSuiteCreate`: Includes `JudgeConfig`.
- `EvaluationSuiteResponse`: Redacts sensitive fields if necessary.
- `EvaluationTestCaseCreate`, `EvaluationTestCaseResponse`
- `EvaluationCreate`, `EvaluationResponse`
- `EvaluationResultResponse`

## 4. Service Logic (`app/services/evaluation_service.py` & `app/services/llm_factory.py`)

### 4.1 LLM Factory (`app/services/llm_factory.py`)
- `get_llm_client(config: JudgeConfig) -> BaseLLMClient`
- If `api_key` is missing in `config`, the factory will attempt to load it from `os.environ` (e.g., `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

### 4.2 Trigger Evaluation
- Validates agent and suite.
- Creates `Evaluation` record.

### 4.3 Execute Evaluation
- **Step 1: Agent Invocation**: Call the target agent.
- **Step 2: Judge Invocation**: 
    - Use `LLMFactory` to get the judge client.
    - Send structured prompt to Judge.
    - Expect JSON response: `{"score": 0.0-1.0, "reasoning": "..."}`.
- **Step 3: Recording**: Save `EvaluationResult`.
- **Step 4: Completion**: 
    - Aggregate results.
    - If all tests pass (score >= threshold), update Agent status to `PENDING_APPROVAL`.
    - If any test fails, update Agent status to `EVALUATION_FAILED`.

## 5. Security Considerations
- **Environment Variables**: Sensitive API keys should ideally be set in the `.env` file.
- **Redaction**: Ensure API keys are not logged or returned in plain text via the API unless necessary for management.

## 6. API Endpoints (`app/api/evaluations.py`)
- `POST /v1/agents/{id}/evaluations`
- `GET /v1/agents/{id}/evaluations`
- `GET /v1/agents/{id}/evaluations/{eval_id}`
- `GET /v1/evaluation-suites`
- `POST /v1/evaluation-suites`
- `GET /v1/evaluation-suites/{id}`
- `POST /v1/evaluation-suites/{id}/test-cases`

## 7. Implementation Steps
1.  **Dependencies**: Add `openai`, `anthropic`, `google-generativeai`, `python-dotenv` to `requirements.txt`.
2.  **Database Migration**: Create evaluation-related tables.
3.  **LLM Factory**: Implement provider adapters.
4.  **Service Layer**: Implement logic to call Agent -> Call Judge -> Record.
5.  **API Routes**: Implement REST endpoints.
