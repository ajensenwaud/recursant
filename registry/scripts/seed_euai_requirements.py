"""Seed the compliance_requirements table with EU AI Act requirements."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app, db
from app.models.euai import ComplianceRequirement, EvidenceType

REQUIREMENTS = [
    # Article 9 - Risk management system
    {
        'id': 'EUAI-ART9-001',
        'article_reference': 'Article 9(1)',
        'title': 'Risk management system established',
        'description': 'A risk management system shall be established, implemented, documented and maintained for high-risk AI systems.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'agent.risk_tier',
        'guidance': 'Ensure the agent has a risk tier assigned and documented risk management procedures.',
    },
    {
        'id': 'EUAI-ART9-002',
        'article_reference': 'Article 9(2)',
        'title': 'Risk identification and analysis',
        'description': 'Known and reasonably foreseeable risks shall be identified and analysed.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'security_scans',
        'guidance': 'Run security scans to identify vulnerabilities and threats.',
    },
    {
        'id': 'EUAI-ART9-003',
        'article_reference': 'Article 9(4)',
        'title': 'Risk mitigation measures',
        'description': 'Risk management measures shall be adopted to eliminate or reduce risks.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document risk mitigation strategies for identified risks.',
    },
    {
        'id': 'EUAI-ART9-004',
        'article_reference': 'Article 9(5)',
        'title': 'Testing for risk management',
        'description': 'Testing shall be performed to ensure the AI system performs consistently and is fit for purpose.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'evaluations',
        'guidance': 'Evaluation results demonstrate fitness for purpose.',
    },
    # Article 10 - Data governance (manual)
    {
        'id': 'EUAI-ART10-001',
        'article_reference': 'Article 10(2)',
        'title': 'Training data governance',
        'description': 'Training, validation and testing data sets shall be subject to appropriate data governance and management practices.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document data governance practices for training datasets.',
    },
    {
        'id': 'EUAI-ART10-002',
        'article_reference': 'Article 10(3)',
        'title': 'Data relevance and representativeness',
        'description': 'Training data shall be relevant, sufficiently representative, and to the best extent possible, free of errors and complete.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document measures taken to ensure data quality.',
    },
    # Article 11 - Technical documentation
    {
        'id': 'EUAI-ART11-001',
        'article_reference': 'Article 11(1)',
        'title': 'Technical documentation drawn up',
        'description': 'Technical documentation shall be drawn up before the AI system is placed on the market or put into service.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'annex_iv_documents',
        'guidance': 'Generate Annex IV documentation with all required sections.',
    },
    {
        'id': 'EUAI-ART11-002',
        'article_reference': 'Article 11(1)',
        'title': 'Documentation kept up-to-date',
        'description': 'Technical documentation shall be kept up to date.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'annex_iv_documents',
        'guidance': 'Regenerate documentation when underlying data changes.',
    },
    # Article 12 - Record-keeping
    {
        'id': 'EUAI-ART12-001',
        'article_reference': 'Article 12(1)',
        'title': 'Automatic logging capabilities',
        'description': 'High-risk AI systems shall technically allow for automatic recording of events (logs).',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'audit_logs',
        'guidance': 'Audit logs automatically capture all lifecycle events.',
    },
    {
        'id': 'EUAI-ART12-002',
        'article_reference': 'Article 12(2)',
        'title': 'Traceability of operations',
        'description': 'Logging capabilities shall ensure traceability of the AI system throughout its lifecycle.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'audit_logs',
        'guidance': 'Hash-chained audit logs provide tamper-evident traceability.',
    },
    # Article 13 - Transparency
    {
        'id': 'EUAI-ART13-001',
        'article_reference': 'Article 13(1)',
        'title': 'Transparency and information provision',
        'description': 'High-risk AI systems shall be designed and developed to ensure their operation is sufficiently transparent.',
        'applicable_risk_categories': ['high', 'limited'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'agent.description',
        'guidance': 'Agent must have clear description of purpose and capabilities.',
    },
    {
        'id': 'EUAI-ART13-002',
        'article_reference': 'Article 13(3)',
        'title': 'Instructions for use',
        'description': 'Instructions for use shall include information on capabilities, limitations, and intended purpose.',
        'applicable_risk_categories': ['high', 'limited'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'agent.capabilities',
        'guidance': 'Capabilities with descriptions serve as usage instructions.',
    },
    # Article 14 - Human oversight
    {
        'id': 'EUAI-ART14-001',
        'article_reference': 'Article 14(1)',
        'title': 'Human oversight measures',
        'description': 'High-risk AI systems shall be designed to be effectively overseen by natural persons.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'guardrail_assignments',
        'guidance': 'Guardrails with human-in-the-loop enforcement provide oversight.',
    },
    {
        'id': 'EUAI-ART14-002',
        'article_reference': 'Article 14(4)',
        'title': 'Ability to override or intervene',
        'description': 'Persons overseeing the AI system shall be able to decide not to use the system or override its output.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document procedures for human override and intervention.',
    },
    # Article 15 - Accuracy, robustness, cybersecurity
    {
        'id': 'EUAI-ART15-001',
        'article_reference': 'Article 15(1)',
        'title': 'Appropriate level of accuracy',
        'description': 'High-risk AI systems shall be designed to achieve an appropriate level of accuracy.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'evaluations',
        'guidance': 'Evaluation scores demonstrate accuracy levels.',
    },
    {
        'id': 'EUAI-ART15-002',
        'article_reference': 'Article 15(4)',
        'title': 'Cybersecurity resilience',
        'description': 'High-risk AI systems shall be resilient against attempts to alter their use or performance.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'security_scans',
        'guidance': 'Security scan results demonstrate cybersecurity resilience.',
    },
    {
        'id': 'EUAI-ART15-003',
        'article_reference': 'Article 15(5)',
        'title': 'Robustness against adversarial attacks',
        'description': 'High-risk AI systems shall be robust against adversarial attacks.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'adversarial_test_runs',
        'guidance': 'Adversarial testing with low evasion rates demonstrates robustness.',
    },
    # Article 17 - Quality management system
    {
        'id': 'EUAI-ART17-001',
        'article_reference': 'Article 17(1)',
        'title': 'Quality management system',
        'description': 'Providers of high-risk AI systems shall put a quality management system in place.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document quality management policies and procedures.',
    },
    {
        'id': 'EUAI-ART17-002',
        'article_reference': 'Article 17(1)(d)',
        'title': 'Design and development controls',
        'description': 'Quality management system shall cover design, design control and design verification.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document development lifecycle controls.',
    },
    # Article 43 - Conformity assessment
    {
        'id': 'EUAI-ART43-001',
        'article_reference': 'Article 43(1)',
        'title': 'Conformity assessment procedure',
        'description': 'Provider shall follow the applicable conformity assessment procedure.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'conformity_assessments',
        'guidance': 'Complete a conformity assessment with documented evidence.',
    },
    # Article 47 - Declaration of conformity
    {
        'id': 'EUAI-ART47-001',
        'article_reference': 'Article 47(1)',
        'title': 'EU Declaration of Conformity',
        'description': 'Provider shall draw up a written or electronically signed EU Declaration of Conformity.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'conformity_assessments',
        'guidance': 'Issue a signed declaration of conformity.',
    },
    {
        'id': 'EUAI-ART47-002',
        'article_reference': 'Article 47(2)',
        'title': 'Declaration kept updated',
        'description': 'Declaration shall be updated when necessary.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Review and update declaration when system changes.',
    },
    # Article 72 - Post-market monitoring
    {
        'id': 'EUAI-ART72-001',
        'article_reference': 'Article 72(1)',
        'title': 'Post-market monitoring system',
        'description': 'Providers shall establish a post-market monitoring system proportionate to the nature and risks of the AI system.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'post_market_monitoring_plans',
        'guidance': 'Create a monitoring plan with defined thresholds and intervals.',
    },
    {
        'id': 'EUAI-ART72-002',
        'article_reference': 'Article 72(2)',
        'title': 'Continuous performance monitoring',
        'description': 'The post-market monitoring system shall actively and systematically collect, document and analyse relevant data.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'guardrail_events',
        'guidance': 'Guardrail events provide continuous monitoring data.',
    },
    {
        'id': 'EUAI-ART72-003',
        'article_reference': 'Article 72(3)',
        'title': 'Post-market monitoring plan',
        'description': 'The post-market monitoring plan shall be part of the technical documentation.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'post_market_monitoring_plans',
        'guidance': 'Include monitoring plan in Annex IV documentation.',
    },
    # Annex IV specific sections
    {
        'id': 'EUAI-AIV-1',
        'article_reference': 'Annex IV, Section 1',
        'title': 'General description of the AI system',
        'description': 'A general description of the AI system including intended purpose, developer, date and version.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'agent',
        'guidance': 'Agent metadata provides general description.',
    },
    {
        'id': 'EUAI-AIV-2A',
        'article_reference': 'Annex IV, Section 2(a)',
        'title': 'Development methodology description',
        'description': 'Description of the methods and steps performed for the development of the AI system.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Describe development methodology, tools, and processes.',
    },
    {
        'id': 'EUAI-AIV-2B',
        'article_reference': 'Annex IV, Section 2(b)',
        'title': 'Data requirements and design choices',
        'description': 'Design specifications, data requirements, and decisions about training methodology.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document training data characteristics and design decisions.',
    },
    {
        'id': 'EUAI-AIV-2C',
        'article_reference': 'Annex IV, Section 2(c)',
        'title': 'Validation and testing procedures',
        'description': 'Description of the validation and testing procedures used, including the used data.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'security_scans,evaluations',
        'guidance': 'Security scans and evaluations provide validation evidence.',
    },
    {
        'id': 'EUAI-AIV-3A',
        'article_reference': 'Annex IV, Section 3(a)',
        'title': 'Capabilities and limitations',
        'description': 'Information on accuracy, robustness and cybersecurity metrics.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'evaluations',
        'guidance': 'Evaluation scores provide accuracy metrics.',
    },
    {
        'id': 'EUAI-AIV-3B',
        'article_reference': 'Annex IV, Section 3(b)',
        'title': 'Known and foreseeable risks',
        'description': 'Known or foreseeable circumstances with risks to health, safety, or fundamental rights.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'security_scan_results,adversarial_test_runs',
        'guidance': 'Security failures and adversarial evasion rates identify risks.',
    },
    {
        'id': 'EUAI-AIV-3C',
        'article_reference': 'Annex IV, Section 3(c)',
        'title': 'Human oversight measures',
        'description': 'Description of the human oversight measures.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'guardrail_assignments',
        'guidance': 'Guardrail assignments with enforcement modes demonstrate oversight.',
    },
    {
        'id': 'EUAI-AIV-3D',
        'article_reference': 'Annex IV, Section 3(d)',
        'title': 'Input data specifications',
        'description': 'Specifications on the input data, as appropriate.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'capabilities.input_schema',
        'guidance': 'Capability input schemas define expected inputs.',
    },
    {
        'id': 'EUAI-AIV-4',
        'article_reference': 'Annex IV, Section 4',
        'title': 'Metrics appropriateness',
        'description': 'Description of the appropriateness of the performance metrics.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Justify why chosen metrics are appropriate for the use case.',
    },
    {
        'id': 'EUAI-AIV-5',
        'article_reference': 'Annex IV, Section 5',
        'title': 'Risk management system description',
        'description': 'Detailed description of the risk management system.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'agent.risk_tier,agent.data_sensitivity',
        'guidance': 'Agent risk classification and security policies form the risk management system.',
    },
    {
        'id': 'EUAI-AIV-6',
        'article_reference': 'Annex IV, Section 6',
        'title': 'Changes and lifecycle documentation',
        'description': 'Description of relevant changes made to the system through its lifecycle.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.AUTO,
        'auto_source': 'agent_versions,audit_logs',
        'guidance': 'Version history and audit logs track lifecycle changes.',
    },
    {
        'id': 'EUAI-AIV-7',
        'article_reference': 'Annex IV, Section 7',
        'title': 'Harmonised standards applied',
        'description': 'List of harmonised standards or common specifications applied.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'List applicable standards (ISO 42001, NIST AI RMF, etc.).',
    },
    {
        'id': 'EUAI-AIV-8',
        'article_reference': 'Annex IV, Section 8',
        'title': 'EU Declaration of Conformity reference',
        'description': 'Copy or reference to the EU Declaration of Conformity.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'conformity_assessments',
        'guidance': 'Link to the Declaration of Conformity.',
    },
    {
        'id': 'EUAI-AIV-9',
        'article_reference': 'Annex IV, Section 9',
        'title': 'Post-market monitoring system description',
        'description': 'Description of the post-market monitoring system established.',
        'applicable_risk_categories': ['high'],
        'evidence_type': EvidenceType.HYBRID,
        'auto_source': 'post_market_monitoring_plans,guardrail_events',
        'guidance': 'Monitoring plans and guardrail event data demonstrate post-market monitoring.',
    },
    # Limited risk transparency requirements
    {
        'id': 'EUAI-ART52-001',
        'article_reference': 'Article 50(1)',
        'title': 'AI system interaction disclosure',
        'description': 'Users shall be informed they are interacting with an AI system unless obvious from circumstances.',
        'applicable_risk_categories': ['limited', 'high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document how users are informed about AI interaction.',
    },
    {
        'id': 'EUAI-ART52-002',
        'article_reference': 'Article 50(2)',
        'title': 'AI-generated content marking',
        'description': 'AI-generated content shall be marked as artificially generated or manipulated.',
        'applicable_risk_categories': ['limited', 'high'],
        'evidence_type': EvidenceType.MANUAL,
        'auto_source': None,
        'guidance': 'Document content marking approach.',
    },
]


def seed_requirements():
    app = create_app()
    with app.app_context():
        # Create tables if needed
        db.create_all()

        count = 0
        for req_data in REQUIREMENTS:
            existing = ComplianceRequirement.query.get(req_data['id'])
            if existing:
                # Update existing
                existing.article_reference = req_data['article_reference']
                existing.title = req_data['title']
                existing.description = req_data['description']
                existing.applicable_risk_categories = req_data['applicable_risk_categories']
                existing.evidence_type = req_data['evidence_type']
                existing.auto_source = req_data['auto_source']
                existing.guidance = req_data['guidance']
            else:
                req = ComplianceRequirement(
                    id=req_data['id'],
                    article_reference=req_data['article_reference'],
                    title=req_data['title'],
                    description=req_data['description'],
                    applicable_risk_categories=req_data['applicable_risk_categories'],
                    evidence_type=req_data['evidence_type'],
                    auto_source=req_data['auto_source'],
                    guidance=req_data['guidance'],
                )
                db.session.add(req)
                count += 1

        db.session.commit()
        total = ComplianceRequirement.query.count()
        print(f"Seeded {count} new requirements ({total} total)")


if __name__ == '__main__':
    seed_requirements()
