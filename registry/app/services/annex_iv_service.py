import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from app import db
from app.models.euai import (
    AnnexIVDocument,
    AnnexIVDocumentStatus,
    EUAIClassification,
)

logger = logging.getLogger(__name__)


class AnnexIVServiceError(Exception):
    pass


class AnnexIVNotFoundError(AnnexIVServiceError):
    pass


class AnnexIVService:

    @staticmethod
    def generate_document(agent_id, tenant_id='default', generated_by=None):
        from app.models.agent import Agent, AgentVersion, Capability
        from app.models.security import SecurityScan, SecurityScanResult, ScanStatus
        from app.models.evaluation import Evaluation, EvaluationResult, EvaluationStatus
        from app.models.guardrail import Guardrail, GuardrailAssignment
        from app.models.audit import AuditLog
        from app.models.adversarial import AdversarialTestRun

        agent = Agent.query.get(agent_id)
        if not agent:
            raise AnnexIVServiceError(f"Agent {agent_id} not found")

        classification = EUAIClassification.query.filter_by(agent_id=agent_id).first()

        # Determine next version
        latest = AnnexIVDocument.query.filter_by(agent_id=agent_id).order_by(
            AnnexIVDocument.version.desc()
        ).first()
        next_version = (latest.version + 1) if latest else 1

        # Supersede previous version
        if latest and latest.status != AnnexIVDocumentStatus.SUPERSEDED:
            latest.status = AnnexIVDocumentStatus.SUPERSEDED

        # Build auto-populated sections
        document_data = AnnexIVService._build_document_data(
            agent, classification, agent_id
        )

        doc = AnnexIVDocument(
            agent_id=agent_id,
            tenant_id=tenant_id,
            version=next_version,
            status=AnnexIVDocumentStatus.DRAFT,
            document_data=document_data,
            manual_sections={},
            generated_by=generated_by,
        )

        # Carry forward manual sections from previous version
        if latest and latest.manual_sections:
            doc.manual_sections = latest.manual_sections.copy()

        db.session.add(doc)
        db.session.commit()

        logger.info(f"Generated Annex IV v{next_version} for agent {agent_id}")
        return doc

    @staticmethod
    def _build_document_data(agent, classification, agent_id):
        from app.models.agent import AgentVersion
        from app.models.security import SecurityScan, SecurityScanResult, ScanStatus
        from app.models.evaluation import Evaluation, EvaluationResult, EvaluationStatus
        from app.models.guardrail import GuardrailAssignment
        from app.models.audit import AuditLog
        from app.models.adversarial import AdversarialTestRun

        capabilities = [
            {
                'name': c.name,
                'description': c.description,
                'input_schema': c.input_schema,
                'output_schema': c.output_schema,
            }
            for c in agent.capabilities
        ]

        # Section 1: General description (auto + manual parts)
        section_1 = {
            'agent_name': agent.name,
            'agent_version': agent.version,
            'description': agent.description,
            'capabilities': capabilities,
            'endpoint_type': agent.endpoint_type.value if agent.endpoint_type else None,
            'risk_tier': agent.risk_tier.value if agent.risk_tier else None,
            'data_sensitivity': agent.data_sensitivity.value if agent.data_sensitivity else None,
            'eu_risk_category': classification.eu_risk_category.value if classification else None,
            'use_domain': classification.use_domain.value if classification else None,
        }

        # Section 2a: Development methodology (mostly manual)
        versions = AgentVersion.query.filter_by(agent_id=agent_id).order_by(
            AgentVersion.created_at.desc()
        ).limit(10).all()
        section_2a = {
            'version_history': [
                {
                    'version': v.version,
                    'created_at': v.created_at.isoformat() if v.created_at else None,
                }
                for v in versions
            ],
        }

        # Section 2c: Validation and testing (fully auto)
        scans = SecurityScan.query.filter_by(agent_id=agent_id).order_by(
            SecurityScan.created_at.desc()
        ).limit(5).all()
        evals = Evaluation.query.filter_by(agent_id=agent_id).order_by(
            Evaluation.created_at.desc()
        ).limit(5).all()
        adversarial_runs = AdversarialTestRun.query.filter_by(agent_id=agent_id).order_by(
            AdversarialTestRun.created_at.desc()
        ).limit(5).all()

        section_2c = {
            'security_scans': [
                {
                    'id': str(s.id),
                    'status': s.status.value,
                    'all_blocking_passed': s.all_blocking_passed,
                    'total_tests': s.total_tests,
                    'passed_tests': s.passed_tests,
                    'failed_tests': s.failed_tests,
                    'created_at': s.created_at.isoformat() if s.created_at else None,
                }
                for s in scans
            ],
            'evaluations': [
                {
                    'id': str(e.id),
                    'status': e.status.value,
                    'weighted_score': float(e.weighted_score) if e.weighted_score else None,
                    'all_blocking_passed': e.all_blocking_passed,
                    'created_at': e.created_at.isoformat() if e.created_at else None,
                }
                for e in evals
            ],
            'adversarial_test_runs': [
                {
                    'id': str(r.id),
                    'status': r.status,
                    'summary': r.summary,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                }
                for r in adversarial_runs
            ],
        }

        # Section 3a: Accuracy metrics (auto from evaluations)
        section_3a = {
            'evaluation_scores': [
                {
                    'id': str(e.id),
                    'weighted_score': float(e.weighted_score) if e.weighted_score else None,
                    'all_blocking_passed': e.all_blocking_passed,
                }
                for e in evals
            ],
        }

        # Section 3b: Known risks (auto from scan failures, adversarial)
        failed_scan_results = []
        if scans:
            from app.models.security import SecurityScanResult, ScanResultStatus
            results = SecurityScanResult.query.filter(
                SecurityScanResult.scan_id.in_([s.id for s in scans]),
                SecurityScanResult.status == ScanResultStatus.FAIL,
            ).limit(20).all()
            failed_scan_results = [
                {
                    'test_case_name': r.test_case_name,
                    'category': r.category,
                    'severity': r.severity.value if r.severity else None,
                    'details': r.details,
                }
                for r in results
            ]

        section_3b = {
            'failed_security_tests': failed_scan_results,
            'adversarial_evasion_rates': [
                {
                    'id': str(r.id),
                    'evasion_rate': r.summary.get('evasion_rate') if r.summary else None,
                }
                for r in adversarial_runs
            ],
        }

        # Section 3c: Human oversight (auto from guardrails)
        assignments = GuardrailAssignment.query.filter_by(agent_id=agent_id).all()
        section_3c = {
            'guardrail_assignments': [
                {
                    'id': str(a.id),
                    'guardrail_id': str(a.guardrail_id),
                    'scope': a.scope.value if a.scope else None,
                    'enforcement_mode': a.enforcement_mode.value if a.enforcement_mode else None,
                }
                for a in assignments
            ],
        }

        # Section 3d: Input specifications (auto from capabilities)
        section_3d = {
            'capability_schemas': [
                {
                    'name': c.name,
                    'input_schema': c.input_schema,
                    'output_schema': c.output_schema,
                }
                for c in agent.capabilities
            ],
        }

        # Section 5: Risk management (auto from agent metadata)
        section_5 = {
            'risk_tier': agent.risk_tier.value if agent.risk_tier else None,
            'data_sensitivity': agent.data_sensitivity.value if agent.data_sensitivity else None,
            'classification': agent.classification.value if agent.classification else None,
        }

        # Section 6: Lifecycle changes (fully auto)
        audit_entries = AuditLog.query.filter(
            AuditLog.detail['agent_id'].as_string() == str(agent_id)
        ).order_by(AuditLog.created_at.desc()).limit(50).all()
        section_6 = {
            'audit_trail': [
                {
                    'action': a.action,
                    'entity_type': a.entity_type,
                    'created_at': a.created_at.isoformat() if a.created_at else None,
                    'performed_by': a.performed_by,
                }
                for a in audit_entries
            ],
            'version_count': AgentVersion.query.filter_by(agent_id=agent_id).count(),
        }

        # Section 9: Post-market monitoring (auto from guardrail events)
        from app.models.guardrail import GuardrailEvent
        recent_events_count = GuardrailEvent.query.filter_by(agent_id=agent_id).count()
        section_9 = {
            'guardrail_events_total': recent_events_count,
            'adversarial_test_count': len(adversarial_runs),
        }

        return {
            'section_1_general_description': section_1,
            'section_2a_development': section_2a,
            'section_2b_data_requirements': {},  # manual
            'section_2c_validation_testing': section_2c,
            'section_3a_accuracy': section_3a,
            'section_3b_known_risks': section_3b,
            'section_3c_human_oversight': section_3c,
            'section_3d_input_specs': section_3d,
            'section_4_metrics': {},  # manual
            'section_5_risk_management': section_5,
            'section_6_lifecycle': section_6,
            'section_7_standards': {},  # manual
            'section_8_declaration': {},  # from conformity assessment
            'section_9_post_market': section_9,
        }

    @staticmethod
    def get_documents(agent_id):
        return AnnexIVDocument.query.filter_by(agent_id=agent_id).order_by(
            AnnexIVDocument.version.desc()
        ).all()

    @staticmethod
    def get_document(document_id):
        doc = AnnexIVDocument.query.get(document_id)
        if not doc:
            raise AnnexIVNotFoundError(f"Document {document_id} not found")
        return doc

    @staticmethod
    def update_manual_sections(document_id, manual_sections):
        doc = AnnexIVDocument.query.get(document_id)
        if not doc:
            raise AnnexIVNotFoundError(f"Document {document_id} not found")

        if doc.status == AnnexIVDocumentStatus.APPROVED:
            raise AnnexIVServiceError("Cannot edit an approved document")

        # Merge new sections into existing
        existing = doc.manual_sections or {}
        existing.update(manual_sections)
        doc.manual_sections = existing

        db.session.commit()
        return doc

    @staticmethod
    def regenerate_auto_sections(document_id):
        doc = AnnexIVDocument.query.get(document_id)
        if not doc:
            raise AnnexIVNotFoundError(f"Document {document_id} not found")

        if doc.status == AnnexIVDocumentStatus.APPROVED:
            raise AnnexIVServiceError("Cannot regenerate an approved document")

        from app.models.agent import Agent
        agent = Agent.query.get(doc.agent_id)
        classification = EUAIClassification.query.filter_by(agent_id=doc.agent_id).first()

        doc.document_data = AnnexIVService._build_document_data(
            agent, classification, doc.agent_id
        )
        db.session.commit()

        logger.info(f"Regenerated auto sections for document {document_id}")
        return doc

    @staticmethod
    def approve_document(document_id, approved_by):
        doc = AnnexIVDocument.query.get(document_id)
        if not doc:
            raise AnnexIVNotFoundError(f"Document {document_id} not found")

        doc.status = AnnexIVDocumentStatus.APPROVED
        doc.approved_by = approved_by
        doc.approved_at = datetime.now(timezone.utc)

        # Sign the document
        doc.signature = AnnexIVService._sign_document(doc)
        doc.signature_algorithm = 'HMAC-SHA256'

        db.session.commit()
        logger.info(f"Approved Annex IV document {document_id}")
        return doc

    @staticmethod
    def _sign_document(doc):
        secret = os.environ.get('SIGNING_SECRET', 'recursant-default-signing-key')
        content = json.dumps(
            {
                'document_id': str(doc.id),
                'agent_id': str(doc.agent_id),
                'version': doc.version,
                'document_data': doc.document_data,
                'manual_sections': doc.manual_sections,
            },
            sort_keys=True,
            default=str,
        )
        return hmac.new(
            secret.encode(), content.encode(), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def generate_pdf(document_id):
        doc = AnnexIVDocument.query.get(document_id)
        if not doc:
            raise AnnexIVNotFoundError(f"Document {document_id} not found")

        from app.services.pdf_generator import PDFGenerator
        pdf_path = PDFGenerator.generate_annex_iv_pdf(doc)

        doc.pdf_storage_path = pdf_path
        db.session.commit()

        return pdf_path
