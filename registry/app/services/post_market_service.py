import logging
from datetime import datetime, timezone, timedelta

from app import db
from app.models.euai import (
    PostMarketMonitoringPlan,
    MonitoringPlanStatus,
)

logger = logging.getLogger(__name__)


class PostMarketServiceError(Exception):
    pass


class MonitoringPlanNotFoundError(PostMarketServiceError):
    pass


class PostMarketService:

    @staticmethod
    def create_plan(agent_id, data, tenant_id='default', created_by=None):
        plan = PostMarketMonitoringPlan(
            agent_id=agent_id,
            tenant_id=tenant_id,
            monitoring_config=data['monitoring_config'],
            status=MonitoringPlanStatus.ACTIVE,
            created_by=created_by,
        )

        db.session.add(plan)
        db.session.commit()

        logger.info(f"Created monitoring plan for agent {agent_id}")
        return plan

    @staticmethod
    def get_plan(agent_id):
        plan = PostMarketMonitoringPlan.query.filter_by(
            agent_id=agent_id
        ).order_by(PostMarketMonitoringPlan.created_at.desc()).first()
        if not plan:
            raise MonitoringPlanNotFoundError(f"No monitoring plan for agent {agent_id}")
        return plan

    @staticmethod
    def update_plan_status(plan_id, new_status):
        plan = PostMarketMonitoringPlan.query.get(plan_id)
        if not plan:
            raise MonitoringPlanNotFoundError(f"Plan {plan_id} not found")

        plan.status = MonitoringPlanStatus(new_status)
        db.session.commit()
        return plan

    @staticmethod
    def generate_report(agent_id, days=30):
        from app.models.guardrail import GuardrailEvent
        from app.models.adversarial import AdversarialTestRun
        from app.models.security import SecurityScan

        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=days)

        # Guardrail events
        events = GuardrailEvent.query.filter(
            GuardrailEvent.agent_id == agent_id,
            GuardrailEvent.timestamp >= period_start,
        ).all()

        event_summary = {
            'total': len(events),
            'by_action': {},
            'by_guardrail': {},
        }
        for e in events:
            action = e.action or 'unknown'
            event_summary['by_action'][action] = event_summary['by_action'].get(action, 0) + 1
            g_id = str(e.guardrail_id) if e.guardrail_id else 'unknown'
            event_summary['by_guardrail'][g_id] = event_summary['by_guardrail'].get(g_id, 0) + 1

        # Adversarial test runs
        adv_runs = AdversarialTestRun.query.filter(
            AdversarialTestRun.agent_id == agent_id,
            AdversarialTestRun.created_at >= period_start,
        ).all()

        adv_summary = {
            'total_runs': len(adv_runs),
            'evasion_rates': [
                {
                    'id': str(r.id),
                    'evasion_rate': r.summary.get('evasion_rate') if r.summary else None,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                }
                for r in adv_runs
            ],
        }

        # Security scans
        scans = SecurityScan.query.filter(
            SecurityScan.agent_id == agent_id,
            SecurityScan.created_at >= period_start,
        ).all()

        scan_summary = {
            'total_scans': len(scans),
            'results': [
                {
                    'id': str(s.id),
                    'all_blocking_passed': s.all_blocking_passed,
                    'created_at': s.created_at.isoformat() if s.created_at else None,
                }
                for s in scans
            ],
        }

        # Simple drift analysis
        drift = {}
        if len(adv_runs) >= 2:
            rates = [
                r.summary.get('evasion_rate', 0)
                for r in adv_runs
                if r.summary and 'evasion_rate' in r.summary
            ]
            if len(rates) >= 2:
                drift['evasion_rate_trend'] = 'increasing' if rates[0] > rates[-1] else 'stable_or_decreasing'

        # Update plan's last report timestamp
        plan = PostMarketMonitoringPlan.query.filter_by(agent_id=agent_id).first()
        if plan:
            plan.last_report_at = now
            db.session.commit()

        report = {
            'agent_id': str(agent_id),
            'period_start': period_start.isoformat(),
            'period_end': now.isoformat(),
            'guardrail_events': event_summary,
            'adversarial_results': adv_summary,
            'security_scans': scan_summary,
            'drift_analysis': drift,
            'generated_at': now.isoformat(),
        }

        logger.info(f"Generated monitoring report for agent {agent_id}")
        return report
