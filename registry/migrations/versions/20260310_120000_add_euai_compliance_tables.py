"""Add EU AI Act compliance tables.

Revision ID: 20260310_120000
Revises: 20260228_180000
Create Date: 2026-03-10 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '20260310_120000'
down_revision = '20260228_180000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    # EU AI Act Classification
    if not _table_exists('euai_classifications'):
        op.create_table(
            'euai_classifications',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', UUID(as_uuid=True),
                      sa.ForeignKey('agents.id'), nullable=False, unique=True),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('eu_risk_category', sa.Enum(
                'unacceptable', 'high', 'limited', 'minimal',
                name='euairiskcategory'), nullable=False),
            sa.Column('use_domain', sa.Enum(
                'biometrics', 'critical_infrastructure', 'education', 'employment',
                'essential_services', 'law_enforcement', 'migration_border',
                'justice_democracy', 'general',
                name='euaiusedomain'), nullable=False, server_default='general'),
            sa.Column('questionnaire_responses', JSONB, nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column('classification_rationale', sa.Text, nullable=True),
            sa.Column('is_confirmed', sa.Boolean, server_default=sa.text('false')),
            sa.Column('classified_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )
        op.create_index('ix_euai_classifications_tenant', 'euai_classifications', ['tenant_id'])

    # Compliance Requirements (reference table)
    if not _table_exists('compliance_requirements'):
        op.create_table(
            'compliance_requirements',
            sa.Column('id', sa.String(50), primary_key=True),
            sa.Column('article_reference', sa.String(100), nullable=False),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('description', sa.Text, nullable=False),
            sa.Column('applicable_risk_categories', JSONB, nullable=False,
                      server_default=sa.text("'[]'::jsonb")),
            sa.Column('evidence_type', sa.Enum(
                'auto', 'manual', 'hybrid',
                name='evidencetype'), nullable=False, server_default='manual'),
            sa.Column('auto_source', sa.String(255), nullable=True),
            sa.Column('guidance', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )

    # Compliance Status (per-agent, per-requirement)
    if not _table_exists('compliance_statuses'):
        op.create_table(
            'compliance_statuses',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', UUID(as_uuid=True),
                      sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('requirement_id', sa.String(50),
                      sa.ForeignKey('compliance_requirements.id'), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('status', sa.Enum(
                'not_started', 'in_progress', 'compliant', 'non_compliant',
                'not_applicable', 'waived',
                name='compliancestatusvalue'), nullable=False, server_default='not_started'),
            sa.Column('evidence_data', JSONB, nullable=True),
            sa.Column('notes', sa.Text, nullable=True),
            sa.Column('last_assessed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('assessed_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.UniqueConstraint('agent_id', 'requirement_id', name='uq_agent_requirement'),
        )
        op.create_index('ix_compliance_statuses_tenant', 'compliance_statuses', ['tenant_id'])
        op.create_index('ix_compliance_statuses_agent', 'compliance_statuses', ['agent_id'])
        op.create_index('ix_compliance_statuses_status', 'compliance_statuses', ['status'])

    # Annex IV Documents
    if not _table_exists('annex_iv_documents'):
        op.create_table(
            'annex_iv_documents',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', UUID(as_uuid=True),
                      sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('version', sa.Integer, nullable=False, server_default=sa.text('1')),
            sa.Column('status', sa.Enum(
                'draft', 'under_review', 'approved', 'superseded',
                name='annexivdocumentstatus'), nullable=False, server_default='draft'),
            sa.Column('document_data', JSONB, nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column('manual_sections', JSONB, nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column('signature', sa.String(512), nullable=True),
            sa.Column('signature_algorithm', sa.String(50), nullable=True,
                      server_default='HMAC-SHA256'),
            sa.Column('pdf_storage_path', sa.String(1024), nullable=True),
            sa.Column('approved_by', sa.String(255), nullable=True),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('generated_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.UniqueConstraint('agent_id', 'version', name='uq_annex_iv_agent_version'),
        )
        op.create_index('ix_annex_iv_documents_tenant', 'annex_iv_documents', ['tenant_id'])
        op.create_index('ix_annex_iv_documents_agent', 'annex_iv_documents', ['agent_id'])

    # Conformity Assessments
    if not _table_exists('conformity_assessments'):
        op.create_table(
            'conformity_assessments',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', UUID(as_uuid=True),
                      sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('assessment_type', sa.Enum(
                'self', 'third_party',
                name='conformityassessmenttype'), nullable=False, server_default='self'),
            sa.Column('status', sa.Enum(
                'in_progress', 'passed', 'failed', 'withdrawn',
                name='conformityassessmentstatus'), nullable=False, server_default='in_progress'),
            sa.Column('compliance_snapshot', JSONB, nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column('findings', JSONB, nullable=False,
                      server_default=sa.text("'[]'::jsonb")),
            sa.Column('declaration_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('declared_by', sa.String(255), nullable=True),
            sa.Column('document_id', UUID(as_uuid=True),
                      sa.ForeignKey('annex_iv_documents.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )
        op.create_index('ix_conformity_assessments_tenant', 'conformity_assessments', ['tenant_id'])
        op.create_index('ix_conformity_assessments_agent', 'conformity_assessments', ['agent_id'])

    # Post-Market Monitoring Plans
    if not _table_exists('post_market_monitoring_plans'):
        op.create_table(
            'post_market_monitoring_plans',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', UUID(as_uuid=True),
                      sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('monitoring_config', JSONB, nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column('status', sa.Enum(
                'active', 'paused', 'archived',
                name='monitoringplanstatus'), nullable=False, server_default='active'),
            sa.Column('last_report_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )
        op.create_index('ix_post_market_monitoring_tenant', 'post_market_monitoring_plans', ['tenant_id'])
        op.create_index('ix_post_market_monitoring_agent', 'post_market_monitoring_plans', ['agent_id'])


def downgrade():
    op.drop_table('post_market_monitoring_plans')
    op.drop_table('conformity_assessments')
    op.drop_table('annex_iv_documents')
    op.drop_table('compliance_statuses')
    op.drop_table('compliance_requirements')
    op.drop_table('euai_classifications')

    # Drop enums
    for enum_name in [
        'monitoringplanstatus', 'conformityassessmentstatus', 'conformityassessmenttype',
        'annexivdocumentstatus', 'compliancestatusvalue', 'evidencetype',
        'euaiusedomain', 'euairiskcategory',
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
