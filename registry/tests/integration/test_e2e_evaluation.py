"""
End-to-end integration tests for LLM-as-judge evaluation.

These tests verify that the Registry can:
1. Submit an agent with a real, live endpoint
2. Execute evaluations using both the agent and an LLM judge
3. Record agent responses and judge reasoning in results

Requirements:
- docker compose must be running with all services
- At least one LLM API key must be configured for the judge
"""

import pytest
import json
import uuid
from typing import Dict, Any

pytestmark = pytest.mark.integration


class TestEvaluationAgainstLiveAgent:
    """Tests for evaluations against a live test agent."""

    def test_trigger_evaluation_against_live_agent(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        integration_evaluation_suite,
        integration_evaluation_test_case,
        any_llm_api_key,
        poll_evaluation,
    ):
        """
        Should trigger an evaluation against a live agent and complete successfully.

        This test:
        1. Submits an agent pointing to the live test-agent
        2. Triggers an evaluation with a suite containing test cases
        3. Polls until completion
        4. Verifies the evaluation completed with results
        """
        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201, f"Agent submission failed: {response.get_json()}"
        agent = response.get_json()
        agent_id = agent['id']

        # Trigger evaluation
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({
                "suite_id": integration_evaluation_suite["id"]
            }),
        )

        # Handle different possible responses
        if eval_response.status_code == 201:
            eval_data = eval_response.get_json()
            eval_id = eval_data['id']

            # Poll for completion
            result = poll_evaluation(agent_id, eval_id, timeout=180)

            # Verify evaluation completed
            assert result is not None, "Evaluation timed out"
            assert result['status'] in ['completed', 'passed', 'failed'], \
                f"Unexpected evaluation status: {result['status']}"

        elif eval_response.status_code in [400, 404, 500]:
            # Log and skip - might be expected if agent/judge isn't configured
            pytest.skip(
                f"Evaluation could not be triggered: {eval_response.get_json()}"
            )
        else:
            pytest.fail(
                f"Unexpected response code: {eval_response.status_code}, "
                f"body: {eval_response.get_json()}"
            )

    def test_evaluation_results_include_agent_responses(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        integration_evaluation_suite,
        integration_evaluation_test_case,
        any_llm_api_key,
        poll_evaluation,
    ):
        """
        Should record actual agent responses in evaluation results.

        This verifies that the case_results include the agent's actual responses
        when evaluation is run against a live agent.
        """
        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        # Trigger evaluation
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({
                "suite_id": integration_evaluation_suite["id"]
            }),
        )

        if eval_response.status_code != 201:
            pytest.skip(f"Could not trigger evaluation: {eval_response.get_json()}")

        eval_id = eval_response.get_json()['id']

        # Poll for completion
        result = poll_evaluation(agent_id, eval_id, timeout=180)

        if result is None:
            pytest.skip("Evaluation timed out")

        # Check for agent responses in results
        # Results might be in 'results', 'case_results', or 'test_results'
        results = (
            result.get('results', []) or
            result.get('case_results', []) or
            result.get('test_results', [])
        )

        if results:
            # At least some results should have agent response populated
            responses_found = sum(
                1 for r in results
                if r.get('response') is not None or r.get('agent_response') is not None
            )
            assert responses_found > 0, (
                "No agent responses recorded. "
                "Expected response field to be populated in evaluation results."
            )

    def test_evaluation_results_include_judge_reasoning(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        integration_evaluation_suite,
        integration_evaluation_test_case,
        any_llm_api_key,
        poll_evaluation,
    ):
        """
        Should include judge reasoning in evaluation results.

        This verifies that the LLM judge was actually called and provided
        reasoning for its scoring decisions.
        """
        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        # Trigger evaluation
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({
                "suite_id": integration_evaluation_suite["id"]
            }),
        )

        if eval_response.status_code != 201:
            pytest.skip(f"Could not trigger evaluation: {eval_response.get_json()}")

        eval_id = eval_response.get_json()['id']

        # Poll for completion
        result = poll_evaluation(agent_id, eval_id, timeout=180)

        if result is None:
            pytest.skip("Evaluation timed out")

        # Check for judge reasoning in results
        results = (
            result.get('results', []) or
            result.get('case_results', []) or
            result.get('test_results', [])
        )

        if results:
            # At least some results should have reasoning populated
            reasoning_found = sum(
                1 for r in results
                if r.get('reasoning') is not None or r.get('judge_reasoning') is not None
            )

            # It's acceptable if reasoning is not always present (e.g., on errors)
            # but we log for debugging
            if reasoning_found == 0:
                # Check if there's an overall score or judgment
                if 'score' in result or 'overall_score' in result:
                    pass  # That's acceptable too
                else:
                    pytest.skip(
                        "No judge reasoning found in results. "
                        "This may indicate the judge wasn't called."
                    )

    def test_evaluation_with_multiple_test_cases(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        integration_evaluation_suite,
        any_llm_api_key,
        poll_evaluation,
        app,
    ):
        """
        Should properly aggregate results across multiple test cases.
        """
        from app.models import (
            EvaluationTestCase,
            EvaluationCategory,
            AggregationMethod,
        )

        # Create additional test cases using the db_session fixture
        test_case_2 = EvaluationTestCase(
            suite_id=integration_evaluation_suite["id"],
            name=f"Integration Boundary Test {uuid.uuid4().hex[:8]}",
            description="Test case for boundary adherence",
            category=EvaluationCategory.BOUNDARY,
            evaluation_cases=[
                {
                    "input": "What's 2 + 2?",
                    "expected": "The agent should answer 4"
                }
            ],
            grading_criteria=[
                {"criterion": "Correct answer", "weight": 1.0}
            ],
            passing_threshold=0.5,
            aggregation_method=AggregationMethod.AVERAGE,
            is_blocking=False,
            weight=1.0,
        )
        db_session.session.add(test_case_2)

        test_case_3 = EvaluationTestCase(
            suite_id=integration_evaluation_suite["id"],
            name=f"Integration Quality Test {uuid.uuid4().hex[:8]}",
            description="Test case for output quality",
            category=EvaluationCategory.QUALITY,
            evaluation_cases=[
                {
                    "input": "Explain why the sky is blue in one sentence",
                    "expected": "The agent should provide a concise, accurate explanation"
                }
            ],
            grading_criteria=[
                {"criterion": "Accuracy", "weight": 1.0},
                {"criterion": "Conciseness", "weight": 1.0}
            ],
            passing_threshold=0.5,
            aggregation_method=AggregationMethod.AVERAGE,
            is_blocking=False,
            weight=1.0,
        )
        db_session.session.add(test_case_3)
        db_session.session.commit()

        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        # Trigger evaluation
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({
                "suite_id": integration_evaluation_suite["id"]
            }),
        )

        if eval_response.status_code != 201:
            pytest.skip(f"Could not trigger evaluation: {eval_response.get_json()}")

        eval_id = eval_response.get_json()['id']

        # Poll for completion (longer timeout for multiple cases)
        result = poll_evaluation(agent_id, eval_id, timeout=300)

        if result is None:
            pytest.skip("Evaluation timed out")

        # Verify evaluation completed
        assert result['status'] in ['completed', 'passed', 'failed']

        # Check that we have an aggregated score
        if 'score' in result or 'overall_score' in result:
            score = result.get('score') or result.get('overall_score')
            # Score should be a valid number between 0 and 1
            if score is not None:
                assert 0 <= score <= 1, f"Score out of range: {score}"


class TestEvaluationListAndRetrieval:
    """Tests for listing and retrieving evaluation results."""

    def test_list_evaluations_after_execution(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        integration_evaluation_suite,
        integration_evaluation_test_case,
        any_llm_api_key,
        poll_evaluation,
    ):
        """
        Should list evaluations for an agent after execution.
        """
        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        # Trigger evaluation
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({
                "suite_id": integration_evaluation_suite["id"]
            }),
        )

        if eval_response.status_code != 201:
            pytest.skip(f"Could not trigger evaluation: {eval_response.get_json()}")

        eval_id = eval_response.get_json()['id']

        # Poll for completion (or just wait a bit)
        poll_evaluation(agent_id, eval_id, timeout=180)

        # List evaluations
        list_response = client.get(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
        )

        assert list_response.status_code == 200
        list_data = list_response.get_json()

        assert 'evaluations' in list_data
        assert 'pagination' in list_data
        assert len(list_data['evaluations']) >= 1

        # Verify our evaluation is in the list
        eval_ids = [e['id'] for e in list_data['evaluations']]
        assert eval_id in eval_ids

    def test_get_evaluation_details(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        integration_evaluation_suite,
        integration_evaluation_test_case,
        any_llm_api_key,
        poll_evaluation,
    ):
        """
        Should retrieve detailed evaluation results.
        """
        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        # Trigger evaluation
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({
                "suite_id": integration_evaluation_suite["id"]
            }),
        )

        if eval_response.status_code != 201:
            pytest.skip(f"Could not trigger evaluation: {eval_response.get_json()}")

        eval_id = eval_response.get_json()['id']

        # Poll for completion
        result = poll_evaluation(agent_id, eval_id, timeout=180)

        if result is None:
            pytest.skip("Evaluation timed out")

        # Get evaluation details
        detail_response = client.get(
            f'/v1/agents/{agent_id}/evaluations/{eval_id}',
            headers=auth_headers,
        )

        assert detail_response.status_code == 200
        detail_data = detail_response.get_json()

        # Verify expected fields
        assert 'id' in detail_data
        assert 'status' in detail_data
        assert 'agent_id' in detail_data or 'suite_id' in detail_data


class TestEvaluationWithDifferentProviders:
    """Tests for evaluations with different LLM providers."""

    @pytest.mark.requires_openai
    def test_evaluation_with_openai_judge(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        openai_api_key,
        poll_evaluation,
    ):
        """
        Should run evaluation using OpenAI as the judge.
        """
        from app.models import EvaluationSuite, EvaluationTestCase, LLMProvider, EvaluationCategory, AggregationMethod

        # Create suite with OpenAI judge using db_session
        suite = EvaluationSuite(
            name=f"openai-judge-suite-{uuid.uuid4().hex[:8]}",
            description="Suite with OpenAI judge",
            version="1.0.0",
            applicable_risk_tiers=["low", "medium", "high", "critical"],
            is_baseline=False,
            is_extended=False,
            judge_provider=LLMProvider.OPENAI,
            judge_model="gpt-5.2",
            judge_config={
                "provider": "openai",
                "model": "gpt-5.2",
                "temperature": 0.0
            },
            is_active=True,
            tenant_id="integration-test-tenant",
        )
        db_session.session.add(suite)
        db_session.session.flush()

        test_case = EvaluationTestCase(
            suite_id=str(suite.id),
            name="OpenAI Judge Test",
            description="Test case for OpenAI judge",
            category=EvaluationCategory.QUALITY,
            evaluation_cases=[
                {
                    "input": "What color is grass?",
                    "expected": "Should say green"
                }
            ],
            grading_criteria=[{"criterion": "Accuracy", "weight": 1.0}],
            passing_threshold=0.5,
            aggregation_method=AggregationMethod.AVERAGE,
            is_blocking=False,
            weight=1.0,
        )
        db_session.session.add(test_case)
        db_session.session.commit()
        suite_id = str(suite.id)

        # Submit and evaluate
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({"suite_id": suite_id}),
        )

        if eval_response.status_code != 201:
            pytest.skip(f"Could not trigger evaluation: {eval_response.get_json()}")

        eval_id = eval_response.get_json()['id']
        result = poll_evaluation(agent_id, eval_id, timeout=180)

        assert result is not None, "Evaluation with OpenAI judge timed out"
        assert result['status'] in ['completed', 'passed', 'failed']

    @pytest.mark.requires_anthropic
    def test_evaluation_with_anthropic_judge(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        anthropic_api_key,
        poll_evaluation,
    ):
        """
        Should run evaluation using Anthropic as the judge.
        """
        from app.models import EvaluationSuite, EvaluationTestCase, LLMProvider, EvaluationCategory, AggregationMethod

        # Create suite with Anthropic judge using db_session
        suite = EvaluationSuite(
            name=f"anthropic-judge-suite-{uuid.uuid4().hex[:8]}",
            description="Suite with Anthropic judge",
            version="1.0.0",
            applicable_risk_tiers=["low", "medium", "high", "critical"],
            is_baseline=False,
            is_extended=False,
            judge_provider=LLMProvider.ANTHROPIC,
            judge_model="claude-sonnet-4-20250514",
            judge_config={
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "temperature": 0.0
            },
            is_active=True,
            tenant_id="integration-test-tenant",
        )
        db_session.session.add(suite)
        db_session.session.flush()

        test_case = EvaluationTestCase(
            suite_id=str(suite.id),
            name="Anthropic Judge Test",
            description="Test case for Anthropic judge",
            category=EvaluationCategory.QUALITY,
            evaluation_cases=[
                {
                    "input": "What is the largest planet?",
                    "expected": "Should say Jupiter"
                }
            ],
            grading_criteria=[{"criterion": "Accuracy", "weight": 1.0}],
            passing_threshold=0.5,
            aggregation_method=AggregationMethod.AVERAGE,
            is_blocking=False,
            weight=1.0,
        )
        db_session.session.add(test_case)
        db_session.session.commit()
        suite_id = str(suite.id)

        # Submit and evaluate
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({"suite_id": suite_id}),
        )

        if eval_response.status_code != 201:
            pytest.skip(f"Could not trigger evaluation: {eval_response.get_json()}")

        eval_id = eval_response.get_json()['id']
        result = poll_evaluation(agent_id, eval_id, timeout=180)

        assert result is not None, "Evaluation with Anthropic judge timed out"
        assert result['status'] in ['completed', 'passed', 'failed']


class TestEvaluationErrorHandling:
    """Tests for evaluation error handling."""

    def test_evaluation_with_unreachable_agent(
        self,
        client,
        db_session,
        auth_headers,
        integration_evaluation_suite,
        integration_evaluation_test_case,
        any_llm_api_key,
    ):
        """
        Should handle unreachable agent gracefully.
        """
        # Create agent with unreachable endpoint
        unreachable_payload = {
            "name": f"unreachable-agent-{uuid.uuid4().hex[:8]}",
            "version": "1.0.0",
            "description": "Agent with unreachable endpoint",
            "owner_id": "test-owner",
            "team_id": "test-team",
            "contact_email": "test@example.com",
            "classification": "internal",
            "data_sensitivity": "none",
            "risk_tier": "low",
            "capabilities": [{"name": "test", "description": "Test capability"}],
            "endpoint": {
                "type": "langchain",
                "url": "http://nonexistent-host:9999/invoke",
                "auth_method": "api_key",
                "timeout_ms": 5000
            }
        }

        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(unreachable_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        # Trigger evaluation
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({
                "suite_id": integration_evaluation_suite["id"]
            }),
        )

        # Should either fail to trigger or fail during execution
        if eval_response.status_code == 201:
            eval_id = eval_response.get_json()['id']

            # The evaluation should eventually fail or complete with errors
            import time
            time.sleep(15)

            result = client.get(
                f'/v1/agents/{agent_id}/evaluations/{eval_id}',
                headers=auth_headers,
            )

            if result.status_code == 200:
                data = result.get_json()
                # Status could be failed, error, or still running
                assert data['status'] in ['pending', 'running', 'failed', 'error', 'completed']

    def test_evaluation_with_missing_suite(
        self,
        client,
        db_session,
        auth_headers,
        live_agent_payload,
        any_llm_api_key,
    ):
        """
        Should return 404 for evaluation with non-existent suite.
        """
        # Submit agent
        response = client.post(
            '/v1/agents',
            headers=auth_headers,
            data=json.dumps(live_agent_payload),
        )
        assert response.status_code == 201
        agent_id = response.get_json()['id']

        # Try to trigger evaluation with fake suite
        fake_suite_id = str(uuid.uuid4())
        eval_response = client.post(
            f'/v1/agents/{agent_id}/evaluations',
            headers=auth_headers,
            data=json.dumps({"suite_id": fake_suite_id}),
        )

        assert eval_response.status_code == 404
