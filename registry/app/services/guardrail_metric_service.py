"""Business logic for the unified guardrail metric store."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app import db
from app.models.guardrail import (
    EnforcementMode,
    Guardrail,
    GuardrailMechanism,
    GuardrailScope,
    GuardrailStatus,
    GuardrailType,
)
from app.models.guardrail_metric import (
    GuardrailMetric,
    GuardrailMetricScore,
    MetricCategory,
)

logger = logging.getLogger(__name__)


class GuardrailMetricServiceError(Exception):
    pass


class GuardrailMetricNotFoundError(GuardrailMetricServiceError):
    pass


class GuardrailMetricValidationError(GuardrailMetricServiceError):
    pass


class GuardrailMetricService:
    """Service for guardrail metric lifecycle management."""

    # --- CRUD ---

    @staticmethod
    def create_metric(data: dict, created_by: str, tenant_id: str = 'default') -> GuardrailMetric:
        metric = GuardrailMetric(
            name=data['name'],
            display_name=data.get('display_name'),
            description=data.get('description'),
            category=MetricCategory(data['category']),
            mechanism=data['mechanism'],
            config=data.get('config', {}),
            version=data.get('version'),
            scoring_rubric=data.get('scoring_rubric'),
            created_by=created_by,
            tenant_id=tenant_id,
        )
        db.session.add(metric)
        db.session.commit()
        logger.info("guardrail_metric_created id=%s name=%s", metric.id, metric.name)
        return metric

    @staticmethod
    def update_metric(metric_id: UUID, data: dict, tenant_id: str = 'default') -> GuardrailMetric:
        metric = GuardrailMetricService._get_or_404(metric_id, tenant_id)

        if metric.is_builtin:
            raise GuardrailMetricValidationError('Built-in metrics cannot be modified')

        for field in ('display_name', 'description', 'category', 'config', 'version', 'scoring_rubric'):
            if field in data:
                value = data[field]
                if field == 'category':
                    value = MetricCategory(value)
                setattr(metric, field, value)

        metric.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("guardrail_metric_updated id=%s", metric.id)
        return metric

    @staticmethod
    def delete_metric(metric_id: UUID, tenant_id: str = 'default') -> GuardrailMetric:
        metric = GuardrailMetricService._get_or_404(metric_id, tenant_id)

        if metric.is_builtin:
            raise GuardrailMetricValidationError('Built-in metrics cannot be deleted')

        metric.soft_delete()
        db.session.commit()
        logger.info("guardrail_metric_deleted id=%s", metric.id)
        return metric

    @staticmethod
    def get_metric(metric_id: UUID, tenant_id: str = 'default') -> GuardrailMetric:
        return GuardrailMetricService._get_or_404(metric_id, tenant_id)

    @staticmethod
    def list_metrics(
        tenant_id: str = 'default',
        category: Optional[str] = None,
        mechanism: Optional[str] = None,
        builtin_only: bool = False,
        page: int = 1,
        per_page: int = 50,
    ):
        query = GuardrailMetric.query.filter(
            GuardrailMetric.tenant_id == tenant_id,
            GuardrailMetric.deleted_at.is_(None),
        )
        if category:
            query = query.filter(GuardrailMetric.category == MetricCategory(category))
        if mechanism:
            query = query.filter(GuardrailMetric.mechanism == mechanism)
        if builtin_only:
            query = query.filter(GuardrailMetric.is_builtin.is_(True))

        return query.order_by(
            GuardrailMetric.is_builtin.desc(),
            GuardrailMetric.name.asc(),
        ).paginate(page=page, per_page=per_page, error_out=False)

    # --- Deploy as guardrail ---

    @staticmethod
    def create_guardrail_from_metric(
        metric_id: UUID,
        data: dict,
        created_by: str,
        tenant_id: str = 'default',
    ) -> Guardrail:
        """Create a new guardrail linked to this metric, inheriting its mechanism and config."""
        metric = GuardrailMetricService._get_or_404(metric_id, tenant_id)

        guardrail = Guardrail(
            name=data['name'],
            description=f'Deployed from metric: {metric.display_name or metric.name}',
            type=GuardrailType(data['type']),
            enforcement_mode=EnforcementMode(data.get('enforcement_mode', 'block')),
            mechanism=GuardrailMechanism(metric.mechanism),
            config=metric.config,
            scope=GuardrailScope(data.get('scope', 'all_agents')),
            priority=data.get('priority', 100),
            version=metric.version,
            metric_id=metric.id,
            created_by=created_by,
            tenant_id=tenant_id,
            status=GuardrailStatus.DRAFT,
        )
        db.session.add(guardrail)
        db.session.commit()
        logger.info(
            "guardrail_from_metric id=%s metric_id=%s",
            guardrail.id, metric.id,
        )
        return guardrail

    # --- Test case generation ---

    @staticmethod
    def generate_eval_test_cases(metric_id: UUID, tenant_id: str = 'default') -> list[dict]:
        """Generate evaluation test cases from a metric's config and rubric."""
        metric = GuardrailMetricService._get_or_404(metric_id, tenant_id)

        test_cases = []
        rubric = metric.scoring_rubric or {}
        criteria = rubric.get('criteria', [])

        if metric.mechanism == 'regex':
            patterns = metric.config.get('patterns', [])
            for p in patterns:
                test_cases.append({
                    'category': metric.category.value,
                    'input_prompt': f'Test input matching: {p.get("name", p.get("pattern", ""))}',
                    'expected_action': p.get('action', 'block'),
                    'metric_id': str(metric.id),
                    'metric_name': metric.name,
                })
        elif metric.mechanism == 'llm_judge':
            # Generate a pass and fail case from rubric criteria
            for criterion in criteria:
                test_cases.append({
                    'category': metric.category.value,
                    'input_prompt': f'Test for criterion: {criterion.get("name", "")}',
                    'expected_behavior': criterion.get('description', ''),
                    'passing_threshold': criterion.get('threshold', 0.7),
                    'metric_id': str(metric.id),
                    'metric_name': metric.name,
                })

        if not test_cases:
            test_cases.append({
                'category': metric.category.value,
                'input_prompt': f'General test for {metric.display_name or metric.name}',
                'expected_action': 'pass',
                'metric_id': str(metric.id),
                'metric_name': metric.name,
            })

        return test_cases

    # --- Score recording ---

    @staticmethod
    def record_score(
        metric_id: UUID,
        agent_name: str,
        score: float,
        source: str = 'evaluation',
        details: Optional[dict] = None,
        tenant_id: str = 'default',
    ) -> GuardrailMetricScore:
        # Verify metric exists
        GuardrailMetricService._get_or_404(metric_id, tenant_id)

        record = GuardrailMetricScore(
            metric_id=metric_id,
            agent_name=agent_name,
            score=score,
            source=source,
            details=details,
            tenant_id=tenant_id,
        )
        db.session.add(record)
        db.session.commit()
        return record

    @staticmethod
    def list_scores(
        metric_id: UUID,
        tenant_id: str = 'default',
        agent_name: Optional[str] = None,
        source: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ):
        query = GuardrailMetricScore.query.filter(
            GuardrailMetricScore.metric_id == metric_id,
            GuardrailMetricScore.tenant_id == tenant_id,
        )
        if agent_name:
            query = query.filter(GuardrailMetricScore.agent_name == agent_name)
        if source:
            query = query.filter(GuardrailMetricScore.source == source)

        return query.order_by(
            GuardrailMetricScore.timestamp.desc(),
        ).paginate(page=page, per_page=per_page, error_out=False)

    # --- Helpers ---

    @staticmethod
    def _get_or_404(metric_id: UUID, tenant_id: str) -> GuardrailMetric:
        metric = GuardrailMetric.query.filter(
            GuardrailMetric.id == metric_id,
            GuardrailMetric.tenant_id == tenant_id,
            GuardrailMetric.deleted_at.is_(None),
        ).first()
        if not metric:
            raise GuardrailMetricNotFoundError(f'Metric {metric_id} not found')
        return metric
