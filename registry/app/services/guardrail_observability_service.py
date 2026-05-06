"""Guardrail observability service for the dashboard.

Aggregates data from the guardrail_events table to power trigger rate charts,
latency breakdowns, top blocked patterns, and drift detection.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, func

from app import db
from app.models.guardrail import GuardrailEvent

logger = logging.getLogger(__name__)


class GuardrailObservabilityService:
    """Aggregation queries over guardrail_events for the observability dashboard."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_query(tenant_id: str):
        """Return a base query scoped to the tenant."""
        return GuardrailEvent.query.filter(
            GuardrailEvent.tenant_id == tenant_id,
        )

    @staticmethod
    def _apply_date_range(query, date_from=None, date_to=None):
        """Apply optional date-range filters to an existing query."""
        if date_from is not None:
            query = query.filter(GuardrailEvent.timestamp >= date_from)
        if date_to is not None:
            query = query.filter(GuardrailEvent.timestamp <= date_to)
        return query

    # ------------------------------------------------------------------
    # 1. Summary
    # ------------------------------------------------------------------

    @staticmethod
    def get_summary(tenant_id: str) -> dict:
        """High-level summary statistics for the tenant's guardrail events.

        Returns dict with: total_events, block_count, block_rate,
        avg_latency_ms, active_guardrails, active_agents, error_count,
        time_range {earliest, latest}.
        """
        base = GuardrailObservabilityService._base_query(tenant_id)

        row = base.with_entities(
            func.count(GuardrailEvent.id).label('total_events'),
            func.count().filter(GuardrailEvent.action == 'block').label('block_count'),
            func.avg(GuardrailEvent.latency_ms).label('avg_latency_ms'),
            func.count(func.distinct(GuardrailEvent.guardrail_name)).label('active_guardrails'),
            func.count(func.distinct(GuardrailEvent.agent_name)).label('active_agents'),
            func.count().filter(GuardrailEvent.is_error.is_(True)).label('error_count'),
            func.min(GuardrailEvent.timestamp).label('earliest'),
            func.max(GuardrailEvent.timestamp).label('latest'),
        ).first()

        total = row.total_events or 0
        block_count = row.block_count or 0
        block_rate = round((block_count / total) * 100, 2) if total else 0.0

        return {
            'total_events': total,
            'block_count': block_count,
            'block_rate': block_rate,
            'avg_latency_ms': round(row.avg_latency_ms, 2) if row.avg_latency_ms else 0.0,
            'active_guardrails': row.active_guardrails or 0,
            'active_agents': row.active_agents or 0,
            'error_count': row.error_count or 0,
            'time_range': {
                'earliest': row.earliest.isoformat() if row.earliest else None,
                'latest': row.latest.isoformat() if row.latest else None,
            },
        }

    # ------------------------------------------------------------------
    # 2. Trigger rates (time-bucketed)
    # ------------------------------------------------------------------

    @staticmethod
    def get_trigger_rates(
        tenant_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        agent_name: Optional[str] = None,
        guardrail_id: Optional[str] = None,
        interval: str = '1h',
    ) -> list[dict]:
        """Time-bucketed event counts broken down by action.

        Uses PostgreSQL ``date_trunc`` for bucketing.  *interval* is mapped
        to a Postgres interval literal (``1h`` -> ``hour``, ``1d`` -> ``day``,
        ``5m`` -> ``5 minutes``, etc.).

        Returns list of {bucket, pass_count, block_count, warn_count,
        redact_count, total}.
        """
        # Map friendly interval strings to Postgres truncation units.
        interval_map = {
            '1m': 'minute',
            '5m': 'minute',
            '15m': 'minute',
            '1h': 'hour',
            '6h': 'hour',
            '1d': 'day',
            '1w': 'week',
        }
        trunc_unit = interval_map.get(interval, 'hour')

        bucket = func.date_trunc(trunc_unit, GuardrailEvent.timestamp).label('bucket')

        pass_count = func.count().filter(GuardrailEvent.action == 'pass').label('pass_count')
        block_count = func.count().filter(GuardrailEvent.action == 'block').label('block_count')
        warn_count = func.count().filter(GuardrailEvent.action == 'warn').label('warn_count')
        redact_count = func.count().filter(GuardrailEvent.action == 'redact').label('redact_count')
        total = func.count(GuardrailEvent.id).label('total')

        query = GuardrailObservabilityService._base_query(tenant_id).with_entities(
            bucket, pass_count, block_count, warn_count, redact_count, total,
        )

        query = GuardrailObservabilityService._apply_date_range(query, date_from, date_to)

        if agent_name:
            query = query.filter(GuardrailEvent.agent_name == agent_name)
        if guardrail_id:
            query = query.filter(GuardrailEvent.guardrail_id == guardrail_id)

        query = query.group_by(bucket).order_by(bucket)

        return [
            {
                'bucket': row.bucket.isoformat() if row.bucket else None,
                'pass_count': row.pass_count or 0,
                'block_count': row.block_count or 0,
                'warn_count': row.warn_count or 0,
                'redact_count': row.redact_count or 0,
                'total': row.total or 0,
            }
            for row in query.all()
        ]

    # ------------------------------------------------------------------
    # 3. Latency breakdown
    # ------------------------------------------------------------------

    @staticmethod
    def get_latency_breakdown(
        tenant_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[dict]:
        """Latency percentiles (p50/p95/p99) per mechanism.

        Uses PostgreSQL ``percentile_cont`` ordered-set aggregate.

        Returns list of {mechanism, p50, p95, p99, avg, count}.
        """
        p50 = func.percentile_cont(0.50).within_group(
            GuardrailEvent.latency_ms,
        ).label('p50')
        p95 = func.percentile_cont(0.95).within_group(
            GuardrailEvent.latency_ms,
        ).label('p95')
        p99 = func.percentile_cont(0.99).within_group(
            GuardrailEvent.latency_ms,
        ).label('p99')
        avg_lat = func.avg(GuardrailEvent.latency_ms).label('avg')
        cnt = func.count(GuardrailEvent.id).label('count')

        query = GuardrailObservabilityService._base_query(tenant_id).with_entities(
            GuardrailEvent.mechanism, p50, p95, p99, avg_lat, cnt,
        )

        query = GuardrailObservabilityService._apply_date_range(query, date_from, date_to)
        query = query.filter(GuardrailEvent.latency_ms.isnot(None))
        query = query.group_by(GuardrailEvent.mechanism)

        return [
            {
                'mechanism': row.mechanism,
                'p50': round(float(row.p50), 2) if row.p50 is not None else None,
                'p95': round(float(row.p95), 2) if row.p95 is not None else None,
                'p99': round(float(row.p99), 2) if row.p99 is not None else None,
                'avg': round(float(row.avg), 2) if row.avg is not None else None,
                'count': row.count or 0,
            }
            for row in query.all()
        ]

    # ------------------------------------------------------------------
    # 4. Top blocked patterns
    # ------------------------------------------------------------------

    @staticmethod
    def get_top_blocked_patterns(
        tenant_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Most frequently matched patterns for non-pass actions.

        Returns list of {pattern, count, percentage} ordered by count
        descending.
        """
        base = GuardrailObservabilityService._base_query(tenant_id).filter(
            GuardrailEvent.action != 'pass',
            GuardrailEvent.matched_pattern.isnot(None),
        )
        base = GuardrailObservabilityService._apply_date_range(base, date_from, date_to)

        # Total non-pass events with a matched pattern (for percentage).
        total_sub = base.with_entities(func.count(GuardrailEvent.id)).scalar() or 0

        rows = (
            base.with_entities(
                GuardrailEvent.matched_pattern.label('pattern'),
                func.count(GuardrailEvent.id).label('count'),
            )
            .group_by(GuardrailEvent.matched_pattern)
            .order_by(func.count(GuardrailEvent.id).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                'pattern': row.pattern,
                'count': row.count,
                'percentage': round((row.count / total_sub) * 100, 2) if total_sub else 0.0,
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # 5. Drift detection
    # ------------------------------------------------------------------

    @staticmethod
    def get_drift_detection(
        tenant_id: str,
        guardrail_id: Optional[str] = None,
        window_days: int = 7,
    ) -> list[dict]:
        """Compare recent vs historical block rates per guardrail.

        *Recent* = events within the last ``window_days`` days.
        *Historical* = events older than ``window_days`` days.

        Returns list of {guardrail_id, guardrail_name, recent_block_rate,
        historical_block_rate, drift_pct, trend}.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=window_days)

        is_recent = GuardrailEvent.timestamp >= cutoff
        is_block = GuardrailEvent.action == 'block'

        recent_total = func.count().filter(is_recent).label('recent_total')
        recent_blocks = func.count().filter(and_(is_recent, is_block)).label('recent_blocks')
        hist_total = func.count().filter(GuardrailEvent.timestamp < cutoff).label('hist_total')
        hist_blocks = func.count().filter(
            and_(GuardrailEvent.timestamp < cutoff, is_block),
        ).label('hist_blocks')

        query = GuardrailObservabilityService._base_query(tenant_id).with_entities(
            GuardrailEvent.guardrail_id,
            GuardrailEvent.guardrail_name,
            recent_total,
            recent_blocks,
            hist_total,
            hist_blocks,
        )

        if guardrail_id:
            query = query.filter(GuardrailEvent.guardrail_id == guardrail_id)

        query = query.group_by(
            GuardrailEvent.guardrail_id,
            GuardrailEvent.guardrail_name,
        )

        results = []
        for row in query.all():
            recent_rate = (
                round((row.recent_blocks / row.recent_total) * 100, 2)
                if row.recent_total else 0.0
            )
            hist_rate = (
                round((row.hist_blocks / row.hist_total) * 100, 2)
                if row.hist_total else 0.0
            )
            drift_pct = round(recent_rate - hist_rate, 2)

            if drift_pct > 2.0:
                trend = 'up'
            elif drift_pct < -2.0:
                trend = 'down'
            else:
                trend = 'stable'

            results.append({
                'guardrail_id': str(row.guardrail_id) if row.guardrail_id else None,
                'guardrail_name': row.guardrail_name,
                'recent_block_rate': recent_rate,
                'historical_block_rate': hist_rate,
                'drift_pct': drift_pct,
                'trend': trend,
            })

        return results
