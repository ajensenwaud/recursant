import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app import db


class AgentStatus(enum.Enum):
    """Agent lifecycle states."""
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    TESTING = 'testing'
    EVALUATING = 'evaluating'
    SECURITY_FAILED = 'security_failed'
    EVALUATION_FAILED = 'evaluation_failed'
    PENDING_APPROVAL = 'pending_approval'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    DECOMMISSIONED = 'decommissioned'


class Classification(enum.Enum):
    """Data classification levels."""
    INTERNAL = 'internal'
    CONFIDENTIAL = 'confidential'
    RESTRICTED = 'restricted'
    PUBLIC = 'public'


class DataSensitivity(enum.Enum):
    """Data sensitivity types."""
    NONE = 'none'
    PII = 'pii'
    PHI = 'phi'
    FINANCIAL = 'financial'
    SECRET = 'secret'


class RiskTier(enum.Enum):
    """Agent risk tiers."""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class EndpointType(enum.Enum):
    """Supported agent endpoint types."""
    LANGCHAIN = 'langchain'
    CREWAI = 'crewai'
    LANGGRAPH = 'langgraph'
    AGENTFORCE = 'agentforce'
    DATABRICKS = 'databricks'
    OPENAI = 'openai'
    OPENCLAW = 'openclaw'
    CUSTOM = 'custom'


class AuthMethod(enum.Enum):
    """Authentication methods for agent endpoints."""
    MTLS = 'mtls'
    OAUTH2 = 'oauth2'
    API_KEY = 'api_key'
    IAM = 'iam'


# Association tables for many-to-many relationships
agent_tools = db.Table(
    'agent_tools',
    db.Column('agent_id', UUID(as_uuid=True), db.ForeignKey('agents.id'), primary_key=True),
    db.Column('tool_id', db.String(255), primary_key=True),
    db.Column('required', db.Boolean, default=True),
)

agent_upstream = db.Table(
    'agent_upstream',
    db.Column('agent_id', UUID(as_uuid=True), db.ForeignKey('agents.id'), primary_key=True),
    db.Column('upstream_agent_id', UUID(as_uuid=True), primary_key=True),
)

agent_downstream = db.Table(
    'agent_downstream',
    db.Column('agent_id', UUID(as_uuid=True), db.ForeignKey('agents.id'), primary_key=True),
    db.Column('downstream_agent_id', UUID(as_uuid=True), primary_key=True),
)


class Agent(db.Model):
    """Main agent entity."""
    __tablename__ = 'agents'

    # Identity
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    version = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)

    # Ownership
    owner_id = db.Column(db.String(255), nullable=False)
    team_id = db.Column(db.String(255), nullable=False)
    contact_email = db.Column(db.String(255), nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')

    # Classification
    classification = db.Column(db.Enum(Classification), nullable=False)
    data_sensitivity = db.Column(db.Enum(DataSensitivity), nullable=False)
    risk_tier = db.Column(db.Enum(RiskTier), nullable=False)

    # Status
    status = db.Column(db.Enum(AgentStatus), nullable=False, default=AgentStatus.DRAFT)

    # Technical Configuration - Endpoint
    endpoint_type = db.Column(db.Enum(EndpointType), nullable=False)
    endpoint_url = db.Column(db.String(2048), nullable=False)
    endpoint_auth_method = db.Column(db.Enum(AuthMethod), nullable=False)
    endpoint_timeout_ms = db.Column(db.Integer, default=30000)
    endpoint_agent_protocol = db.Column(db.String(50), default='A2A')

    # Governance
    guardrail_profile_id = db.Column(db.String(255), nullable=True)
    execution_graph_id = db.Column(db.String(255), nullable=True)

    # Resource quota
    max_tokens_per_request = db.Column(db.Integer, nullable=True)
    max_requests_per_minute = db.Column(db.Integer, nullable=True)
    max_cost_per_day_usd = db.Column(db.Numeric(10, 2), nullable=True)

    # Audit fields
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    capabilities = db.relationship(
        'Capability',
        backref='agent',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    versions = db.relationship(
        'AgentVersion',
        backref='agent',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='AgentVersion.created_at.desc()'
    )
    security_scans = db.relationship(
        'SecurityScan',
        back_populates='agent',
        lazy='dynamic',
        order_by='SecurityScan.created_at.desc()'
    )

    # Unique constraint: name must be unique within tenant (only for non-deleted agents)
    # Implemented as a partial unique index in migration d4e5f6g7h8i9
    __table_args__ = (
        db.Index(
            'uq_tenant_agent_name_active',
            'tenant_id', 'name',
            unique=True,
            postgresql_where=db.text('deleted_at IS NULL'),
        ),
    )

    def __repr__(self):
        return f'<Agent {self.name} v{self.version}>'

    @property
    def is_active(self):
        return self.status == AgentStatus.ACTIVE and self.deleted_at is None

    def soft_delete(self):
        """Soft delete the agent."""
        self.deleted_at = datetime.now(timezone.utc)
        self.status = AgentStatus.DECOMMISSIONED


class AgentVersion(db.Model):
    """Stores historical versions of agents."""
    __tablename__ = 'agent_versions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    version = db.Column(db.String(50), nullable=False)

    # Snapshot of agent state at this version
    snapshot = db.Column(JSON, nullable=False)

    # Audit
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(255), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('agent_id', 'version', name='uq_agent_version'),
    )

    def __repr__(self):
        return f'<AgentVersion {self.agent_id} v{self.version}>'


class Capability(db.Model):
    """Agent capabilities for discovery."""
    __tablename__ = 'capabilities'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)

    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    input_schema = db.Column(JSON, nullable=True)
    output_schema = db.Column(JSON, nullable=True)

    # For semantic search (pgvector embedding will be added later)
    # embedding = db.Column(Vector(1536), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint('agent_id', 'name', name='uq_agent_capability_name'),
    )

    def __repr__(self):
        return f'<Capability {self.name}>'


class ToolDependency(db.Model):
    """Tools that an agent depends on."""
    __tablename__ = 'tool_dependencies'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    tool_id = db.Column(db.String(255), nullable=False)
    required = db.Column(db.Boolean, default=True)

    agent = db.relationship('Agent', backref=db.backref('tool_dependencies', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('agent_id', 'tool_id', name='uq_agent_tool'),
    )


class AgentRelationship(db.Model):
    """Upstream and downstream agent relationships."""
    __tablename__ = 'agent_relationships'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    related_agent_id = db.Column(UUID(as_uuid=True), nullable=False)
    relationship_type = db.Column(db.String(20), nullable=False)  # 'upstream' or 'downstream'

    agent = db.relationship('Agent', backref=db.backref('relationships', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('agent_id', 'related_agent_id', 'relationship_type', name='uq_agent_relationship'),
    )


class GuardrailProfile(db.Model):
    """Guardrail profiles for agent compliance."""
    __tablename__ = 'guardrail_profiles'

    id = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    config = db.Column(JSON, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f'<GuardrailProfile {self.name}>'


class GovernanceConfig(db.Model):
    """Tenant-level governance configuration (e.g. auto-approval settings)."""
    __tablename__ = 'governance_configs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(255), nullable=False, unique=True)
    auto_approve_enabled = db.Column(db.Boolean, default=False, nullable=False)
    auto_approve_risk_tiers = db.Column(JSON, default=list, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f'<GovernanceConfig tenant={self.tenant_id}>'
