import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.euai import (
    EUAIClassification,
    EUAIRiskCategory,
    EUAIUseDomain,
    ComplianceRequirement,
    ComplianceStatus,
    ComplianceStatusValue,
)

logger = logging.getLogger(__name__)


class EUAIComplianceServiceError(Exception):
    pass


class ClassificationNotFoundError(EUAIComplianceServiceError):
    pass


class ClassificationAlreadyExistsError(EUAIComplianceServiceError):
    pass


class RequirementNotFoundError(EUAIComplianceServiceError):
    pass


class EUAIComplianceService:

    @staticmethod
    def get_classification(agent_id):
        classification = EUAIClassification.query.filter_by(agent_id=agent_id).first()
        if not classification:
            raise ClassificationNotFoundError(f"No EU AI Act classification for agent {agent_id}")
        return classification

    @staticmethod
    def classify_agent(agent_id, data, tenant_id='default', classified_by=None):
        existing = EUAIClassification.query.filter_by(agent_id=agent_id).first()
        if existing:
            raise ClassificationAlreadyExistsError(
                f"Agent {agent_id} already has an EU AI Act classification"
            )

        classification = EUAIClassification(
            agent_id=agent_id,
            tenant_id=tenant_id,
            eu_risk_category=EUAIRiskCategory(data['eu_risk_category']),
            use_domain=EUAIUseDomain(data['use_domain']),
            questionnaire_responses=data['questionnaire_responses'],
            classification_rationale=data.get('classification_rationale'),
            is_confirmed=data.get('is_confirmed', False),
            classified_by=classified_by,
        )

        db.session.add(classification)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise EUAIComplianceServiceError(f"Database error: {str(e)}")

        # Create ComplianceStatus records for applicable requirements
        EUAIComplianceService._create_compliance_statuses(
            agent_id, classification.eu_risk_category, tenant_id
        )

        return classification

    @staticmethod
    def update_classification(agent_id, data, classified_by=None):
        classification = EUAIClassification.query.filter_by(agent_id=agent_id).first()
        if not classification:
            raise ClassificationNotFoundError(f"No EU AI Act classification for agent {agent_id}")

        old_category = classification.eu_risk_category

        if 'eu_risk_category' in data:
            classification.eu_risk_category = EUAIRiskCategory(data['eu_risk_category'])
        if 'use_domain' in data:
            classification.use_domain = EUAIUseDomain(data['use_domain'])
        if 'questionnaire_responses' in data:
            classification.questionnaire_responses = data['questionnaire_responses']
        if 'classification_rationale' in data:
            classification.classification_rationale = data['classification_rationale']
        if 'is_confirmed' in data:
            classification.is_confirmed = data['is_confirmed']

        if classified_by:
            classification.classified_by = classified_by

        db.session.commit()

        # If risk category changed, update compliance statuses
        if old_category != classification.eu_risk_category:
            EUAIComplianceService._recreate_compliance_statuses(
                agent_id, classification.eu_risk_category, classification.tenant_id
            )

        return classification

    @staticmethod
    def _create_compliance_statuses(agent_id, risk_category, tenant_id):
        requirements = ComplianceRequirement.query.all()
        category_value = risk_category.value

        for req in requirements:
            applicable = req.applicable_risk_categories or []
            if category_value in applicable:
                status = ComplianceStatus(
                    agent_id=agent_id,
                    requirement_id=req.id,
                    tenant_id=tenant_id,
                    status=ComplianceStatusValue.NOT_STARTED,
                )
                db.session.add(status)

        db.session.commit()

    @staticmethod
    def _recreate_compliance_statuses(agent_id, risk_category, tenant_id):
        # Remove statuses for requirements no longer applicable
        category_value = risk_category.value
        requirements = ComplianceRequirement.query.all()

        applicable_ids = set()
        for req in requirements:
            applicable = req.applicable_risk_categories or []
            if category_value in applicable:
                applicable_ids.add(req.id)

        existing = ComplianceStatus.query.filter_by(agent_id=agent_id).all()
        existing_ids = {s.requirement_id for s in existing}

        # Remove no-longer-applicable
        for s in existing:
            if s.requirement_id not in applicable_ids:
                db.session.delete(s)

        # Add newly applicable
        for req_id in applicable_ids - existing_ids:
            status = ComplianceStatus(
                agent_id=agent_id,
                requirement_id=req_id,
                tenant_id=tenant_id,
                status=ComplianceStatusValue.NOT_STARTED,
            )
            db.session.add(status)

        db.session.commit()

    @staticmethod
    def get_compliance_statuses(agent_id):
        statuses = ComplianceStatus.query.filter_by(agent_id=agent_id).all()
        return statuses

    @staticmethod
    def update_compliance_status(agent_id, requirement_id, data, assessed_by=None):
        status = ComplianceStatus.query.filter_by(
            agent_id=agent_id, requirement_id=requirement_id
        ).first()
        if not status:
            raise RequirementNotFoundError(
                f"No compliance status for agent {agent_id}, requirement {requirement_id}"
            )

        status.status = ComplianceStatusValue(data['status'])
        if 'evidence_data' in data:
            status.evidence_data = data['evidence_data']
        if 'notes' in data:
            status.notes = data['notes']
        status.last_assessed_at = datetime.now(timezone.utc)
        status.assessed_by = assessed_by

        db.session.commit()
        return status

    @staticmethod
    def auto_assess_all(agent_id):
        from app.models.agent import Agent
        from app.models.security import SecurityScan, ScanStatus
        from app.models.evaluation import Evaluation, EvaluationStatus
        from app.models.guardrail import GuardrailAssignment
        from app.models.audit import AuditLog
        from app.models.adversarial import AdversarialTestRun

        agent = Agent.query.get(agent_id)
        if not agent:
            raise EUAIComplianceServiceError(f"Agent {agent_id} not found")

        statuses = ComplianceStatus.query.filter_by(agent_id=agent_id).all()
        if not statuses:
            raise ClassificationNotFoundError(f"Agent {agent_id} has no compliance statuses")

        now = datetime.now(timezone.utc)
        status_map = {s.requirement_id: s for s in statuses}

        # Gather data
        latest_scan = SecurityScan.query.filter_by(agent_id=agent_id).order_by(
            SecurityScan.created_at.desc()
        ).first()

        latest_eval = Evaluation.query.filter_by(agent_id=agent_id).order_by(
            Evaluation.created_at.desc()
        ).first()

        guardrail_assignments = GuardrailAssignment.query.filter_by(agent_id=agent_id).all()

        audit_count = AuditLog.query.filter(
            AuditLog.detail['agent_id'].as_string() == str(agent_id)
        ).count()

        latest_adversarial = AdversarialTestRun.query.filter_by(agent_id=agent_id).order_by(
            AdversarialTestRun.created_at.desc()
        ).first()

        # Apply auto-assessment rules
        assessments = {
            # Art. 9 - Risk management: agent has risk_tier set
            'EUAI-ART9-001': lambda: (
                ComplianceStatusValue.COMPLIANT
                if agent.risk_tier is not None
                else ComplianceStatusValue.NON_COMPLIANT,
                {'risk_tier': agent.risk_tier.value if agent.risk_tier else None}
            ),
            'EUAI-ART9-002': lambda: (
                ComplianceStatusValue.COMPLIANT
                if latest_scan and latest_scan.status == ScanStatus.COMPLETED
                else ComplianceStatusValue.NON_COMPLIANT,
                {'scan_id': str(latest_scan.id) if latest_scan else None}
            ),
            # Art. 11 / Annex IV - Technical documentation
            'EUAI-ART11-001': None,  # manual - methodology narrative
            # Art. 12 - Record-keeping
            'EUAI-ART12-001': lambda: (
                ComplianceStatusValue.COMPLIANT
                if audit_count > 0
                else ComplianceStatusValue.NON_COMPLIANT,
                {'audit_log_count': audit_count}
            ),
            # Art. 13 - Transparency
            'EUAI-ART13-001': lambda: (
                ComplianceStatusValue.COMPLIANT
                if agent.description and len(agent.description) > 10
                else ComplianceStatusValue.NON_COMPLIANT,
                {'has_description': bool(agent.description)}
            ),
            'EUAI-ART13-002': lambda: (
                ComplianceStatusValue.COMPLIANT
                if agent.capabilities.count() > 0
                else ComplianceStatusValue.NON_COMPLIANT,
                {'capability_count': agent.capabilities.count()}
            ),
            # Art. 14 - Human oversight
            'EUAI-ART14-001': lambda: (
                ComplianceStatusValue.COMPLIANT
                if len(guardrail_assignments) > 0
                else ComplianceStatusValue.NON_COMPLIANT,
                {'guardrail_count': len(guardrail_assignments)}
            ),
            # Art. 15 - Accuracy, robustness, cybersecurity
            'EUAI-ART15-001': lambda: (
                ComplianceStatusValue.COMPLIANT
                if latest_eval and latest_eval.status == EvaluationStatus.COMPLETED
                and latest_eval.all_blocking_passed
                else ComplianceStatusValue.NON_COMPLIANT,
                {
                    'eval_id': str(latest_eval.id) if latest_eval else None,
                    'passed': latest_eval.all_blocking_passed if latest_eval else None,
                }
            ),
            'EUAI-ART15-002': lambda: (
                ComplianceStatusValue.COMPLIANT
                if latest_scan and latest_scan.all_blocking_passed
                else ComplianceStatusValue.NON_COMPLIANT,
                {
                    'scan_id': str(latest_scan.id) if latest_scan else None,
                    'passed': latest_scan.all_blocking_passed if latest_scan else None,
                }
            ),
            'EUAI-ART15-003': lambda: (
                ComplianceStatusValue.COMPLIANT
                if latest_adversarial and latest_adversarial.summary
                and latest_adversarial.summary.get('evasion_rate', 1.0) < 0.1
                else ComplianceStatusValue.NON_COMPLIANT,
                {
                    'run_id': str(latest_adversarial.id) if latest_adversarial else None,
                    'evasion_rate': (
                        latest_adversarial.summary.get('evasion_rate')
                        if latest_adversarial and latest_adversarial.summary
                        else None
                    ),
                }
            ),
            # Annex IV Section 2c - Validation/testing
            'EUAI-AIV-2C': lambda: (
                ComplianceStatusValue.COMPLIANT
                if (latest_scan and latest_scan.all_blocking_passed
                    and latest_eval and latest_eval.status == EvaluationStatus.COMPLETED)
                else ComplianceStatusValue.NON_COMPLIANT,
                {
                    'scan_passed': latest_scan.all_blocking_passed if latest_scan else None,
                    'eval_completed': (
                        latest_eval.status == EvaluationStatus.COMPLETED if latest_eval else False
                    ),
                }
            ),
            # Annex IV Section 6 - Lifecycle changes
            'EUAI-AIV-6': lambda: (
                ComplianceStatusValue.COMPLIANT
                if audit_count > 0
                else ComplianceStatusValue.NON_COMPLIANT,
                {'audit_log_count': audit_count}
            ),
        }

        updated_count = 0
        for req_id, assess_fn in assessments.items():
            if req_id in status_map and assess_fn is not None:
                try:
                    new_status, evidence = assess_fn()
                    s = status_map[req_id]
                    s.status = new_status
                    s.evidence_data = evidence
                    s.last_assessed_at = now
                    s.assessed_by = 'auto-assessment'
                    updated_count += 1
                except Exception as e:
                    logger.warning(f"Auto-assess failed for {req_id}: {e}")

        db.session.commit()
        logger.info(f"Auto-assessed {updated_count} requirements for agent {agent_id}")
        return updated_count

    @staticmethod
    def get_gap_analysis(agent_id):
        statuses = ComplianceStatus.query.filter_by(agent_id=agent_id).all()
        if not statuses:
            raise ClassificationNotFoundError(f"Agent {agent_id} has no compliance statuses")

        total = len(statuses)
        compliant = sum(1 for s in statuses if s.status == ComplianceStatusValue.COMPLIANT)
        non_compliant = sum(1 for s in statuses if s.status == ComplianceStatusValue.NON_COMPLIANT)
        not_started = sum(1 for s in statuses if s.status == ComplianceStatusValue.NOT_STARTED)
        in_progress = sum(1 for s in statuses if s.status == ComplianceStatusValue.IN_PROGRESS)
        not_applicable = sum(1 for s in statuses if s.status == ComplianceStatusValue.NOT_APPLICABLE)

        applicable = total - not_applicable
        score = (compliant / applicable * 100) if applicable > 0 else 0.0

        gaps = []
        for s in statuses:
            if s.status in (ComplianceStatusValue.NON_COMPLIANT, ComplianceStatusValue.NOT_STARTED):
                gaps.append({
                    'requirement_id': s.requirement_id,
                    'title': s.requirement.title if s.requirement else '',
                    'article_reference': s.requirement.article_reference if s.requirement else '',
                    'status': s.status.value,
                    'evidence_type': s.requirement.evidence_type.value if s.requirement else '',
                    'auto_source': s.requirement.auto_source if s.requirement else None,
                    'guidance': s.requirement.guidance if s.requirement else None,
                    'notes': s.notes,
                })

        return {
            'agent_id': str(agent_id),
            'compliance_score': round(score, 1),
            'total_requirements': total,
            'compliant_count': compliant,
            'non_compliant_count': non_compliant,
            'not_started_count': not_started,
            'in_progress_count': in_progress,
            'gaps': gaps,
        }

    @staticmethod
    def compute_compliance_score(agent_id):
        statuses = ComplianceStatus.query.filter_by(agent_id=agent_id).all()
        if not statuses:
            return 0.0

        not_applicable = sum(1 for s in statuses if s.status == ComplianceStatusValue.NOT_APPLICABLE)
        applicable = len(statuses) - not_applicable
        if applicable == 0:
            return 100.0

        compliant = sum(1 for s in statuses if s.status == ComplianceStatusValue.COMPLIANT)
        return round(compliant / applicable * 100, 1)

    @staticmethod
    def get_requirements():
        return ComplianceRequirement.query.order_by(ComplianceRequirement.id).all()

    @staticmethod
    def get_dashboard(tenant_id='default'):
        from app.models.agent import Agent

        classifications = EUAIClassification.query.filter_by(tenant_id=tenant_id).all()

        agents_data = []
        category_counts = {}

        for c in classifications:
            agent = Agent.query.get(c.agent_id)
            if not agent or agent.deleted_at is not None:
                continue

            score = EUAIComplianceService.compute_compliance_score(c.agent_id)
            statuses = ComplianceStatus.query.filter_by(agent_id=c.agent_id).all()
            total_applicable = sum(
                1 for s in statuses if s.status != ComplianceStatusValue.NOT_APPLICABLE
            )
            compliant_count = sum(
                1 for s in statuses if s.status == ComplianceStatusValue.COMPLIANT
            )
            gap_count = sum(
                1 for s in statuses
                if s.status in (ComplianceStatusValue.NON_COMPLIANT, ComplianceStatusValue.NOT_STARTED)
            )

            has_annex_iv = AnnexIVDocument.query.filter_by(agent_id=c.agent_id).first() is not None
            has_conformity = ConformityAssessment.query.filter_by(agent_id=c.agent_id).first() is not None

            cat = c.eu_risk_category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

            agents_data.append({
                'agent_id': str(c.agent_id),
                'agent_name': agent.name,
                'eu_risk_category': cat,
                'compliance_score': score,
                'compliant_count': compliant_count,
                'total_applicable': total_applicable,
                'gap_count': gap_count,
                'has_annex_iv': has_annex_iv,
                'has_conformity': has_conformity,
            })

        total = len(agents_data)
        overall_pct = (
            sum(a['compliance_score'] for a in agents_data) / total if total > 0 else 0.0
        )

        return {
            'agents': agents_data,
            'total_agents': total,
            'by_risk_category': category_counts,
            'overall_compliance_pct': round(overall_pct, 1),
        }


# Late import to avoid circular dependency
from app.models.euai import AnnexIVDocument, ConformityAssessment
