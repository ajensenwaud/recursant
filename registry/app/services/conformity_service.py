import logging
from datetime import datetime, timezone

from app import db
from app.models.euai import (
    ConformityAssessment,
    ConformityAssessmentType,
    ConformityAssessmentStatus,
    ComplianceStatus,
    ComplianceStatusValue,
)

logger = logging.getLogger(__name__)


class ConformityServiceError(Exception):
    pass


class ConformityNotFoundError(ConformityServiceError):
    pass


class ConformityService:

    @staticmethod
    def create_assessment(agent_id, data, tenant_id='default'):
        # Freeze current compliance snapshot
        statuses = ComplianceStatus.query.filter_by(agent_id=agent_id).all()
        snapshot = {
            'statuses': [
                {
                    'requirement_id': s.requirement_id,
                    'status': s.status.value,
                    'evidence_data': s.evidence_data,
                    'last_assessed_at': s.last_assessed_at.isoformat() if s.last_assessed_at else None,
                }
                for s in statuses
            ],
            'snapshot_at': datetime.now(timezone.utc).isoformat(),
        }

        assessment = ConformityAssessment(
            agent_id=agent_id,
            tenant_id=tenant_id,
            assessment_type=ConformityAssessmentType(data.get('assessment_type', 'self')),
            status=ConformityAssessmentStatus.IN_PROGRESS,
            compliance_snapshot=snapshot,
            document_id=data.get('document_id'),
        )

        db.session.add(assessment)
        db.session.commit()

        logger.info(f"Created conformity assessment for agent {agent_id}")
        return assessment

    @staticmethod
    def get_assessments(agent_id):
        return ConformityAssessment.query.filter_by(agent_id=agent_id).order_by(
            ConformityAssessment.created_at.desc()
        ).all()

    @staticmethod
    def get_assessment(assessment_id):
        assessment = ConformityAssessment.query.get(assessment_id)
        if not assessment:
            raise ConformityNotFoundError(f"Assessment {assessment_id} not found")
        return assessment

    @staticmethod
    def add_finding(assessment_id, finding_data):
        assessment = ConformityAssessment.query.get(assessment_id)
        if not assessment:
            raise ConformityNotFoundError(f"Assessment {assessment_id} not found")

        if assessment.status != ConformityAssessmentStatus.IN_PROGRESS:
            raise ConformityServiceError("Cannot add findings to a completed assessment")

        findings = list(assessment.findings or [])
        findings.append({
            'finding': finding_data['finding'],
            'severity': finding_data['severity'],
            'requirement_id': finding_data.get('requirement_id'),
            'added_at': datetime.now(timezone.utc).isoformat(),
        })
        assessment.findings = findings

        db.session.commit()
        return assessment

    @staticmethod
    def declare(assessment_id, declared_by):
        assessment = ConformityAssessment.query.get(assessment_id)
        if not assessment:
            raise ConformityNotFoundError(f"Assessment {assessment_id} not found")

        # Check all critical requirements are compliant
        snapshot = assessment.compliance_snapshot or {}
        statuses = snapshot.get('statuses', [])
        critical_failures = [
            s for s in statuses
            if s['status'] in ('non_compliant', 'not_started')
        ]

        if critical_failures:
            raise ConformityServiceError(
                f"Cannot declare conformity: {len(critical_failures)} requirements not met"
            )

        # Check no critical findings
        findings = assessment.findings or []
        critical_findings = [f for f in findings if f.get('severity') == 'critical']
        if critical_findings:
            raise ConformityServiceError(
                f"Cannot declare conformity: {len(critical_findings)} critical findings"
            )

        assessment.status = ConformityAssessmentStatus.PASSED
        assessment.declaration_date = datetime.now(timezone.utc)
        assessment.declared_by = declared_by

        db.session.commit()
        logger.info(f"Conformity declared for assessment {assessment_id}")
        return assessment
