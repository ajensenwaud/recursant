"""Network discovery models — tracks scans, discovered hosts, agents, and tools.

These models support the network discovery feature:
- DiscoveryScan: scheduled or ad-hoc network scans
- DiscoveredHost: hosts found during scans
- DiscoveredAgent: A2A agents discovered on hosts
- DiscoveredTool: MCP tools discovered on hosts
- DiscoveryScanSchedule: recurring scan schedules
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Index
from sqlalchemy.dialects.postgresql import UUID

from app import db


class DiscoveryScanStatus(enum.Enum):
    """Scan lifecycle states."""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class DiscoveryScanType(enum.Enum):
    """Types of discovery scan."""
    NETWORK = 'network'
    KUBERNETES = 'kubernetes'
    DNS = 'dns'


class ServiceType(enum.Enum):
    """Type of service discovered on a host."""
    A2A_AGENT = 'a2a_agent'
    MCP_SERVER = 'mcp_server'
    HTTP_SERVICE = 'http_service'
    UNKNOWN = 'unknown'


class HostStatus(enum.Enum):
    """Reachability status of a discovered host."""
    ONLINE = 'online'
    OFFLINE = 'offline'
    UNREACHABLE = 'unreachable'


class GovernanceStatus(enum.Enum):
    """Governance status of a discovered agent."""
    GOVERNED = 'governed'
    KNOWN_UNGOVERNED = 'known_ungoverned'
    UNKNOWN = 'unknown'
    ONBOARDED = 'onboarded'
    QUARANTINED = 'quarantined'
    DISMISSED = 'dismissed'


class DiscoveredToolStatus(enum.Enum):
    """Governance status of a discovered tool."""
    GOVERNED = 'governed'
    UNGOVERNED = 'ungoverned'
    ONBOARDED = 'onboarded'


class DiscoveryScan(db.Model):
    """A network discovery scan — ad-hoc or scheduled."""

    __tablename__ = 'discovery_scans'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pending')
    scan_type = db.Column(db.String(30), nullable=False)
    config = db.Column(JSON, nullable=False)
    summary = db.Column(JSON, nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index('ix_discovery_scans_tenant', 'tenant_id'),
        Index('ix_discovery_scans_status', 'status'),
        Index('ix_discovery_scans_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<DiscoveryScan {self.name} [{self.status}]>'


class DiscoveredHost(db.Model):
    """A host (IP + port) found during a discovery scan."""

    __tablename__ = 'discovered_hosts'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('discovery_scans.id'),
        nullable=False,
    )
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    address = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    protocol = db.Column(db.String(10), nullable=False, default='http')
    service_type = db.Column(db.String(30), nullable=False, default='unknown')
    tls_info = db.Column(JSON, nullable=True)
    first_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    status = db.Column(db.String(20), nullable=False, default='online')
    metadata_ = db.Column('metadata', JSON, nullable=True)

    scan = db.relationship('DiscoveryScan', backref='hosts')

    __table_args__ = (
        Index('ix_discovered_hosts_tenant', 'tenant_id'),
        Index('ix_discovered_hosts_scan', 'scan_id'),
        Index('ix_discovered_hosts_address_port', 'tenant_id', 'address', 'port', unique=True),
        Index('ix_discovered_hosts_status', 'status'),
    )

    def __repr__(self):
        return f'<DiscoveredHost {self.address}:{self.port} [{self.status}]>'


class DiscoveredAgent(db.Model):
    """An A2A agent discovered on a host."""

    __tablename__ = 'discovered_agents'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('discovered_hosts.id'),
        nullable=False,
    )
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    agent_card = db.Column(JSON, nullable=True)
    name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    version = db.Column(db.String(50), nullable=True)
    framework_type = db.Column(db.String(50), nullable=True)
    governance_status = db.Column(db.String(30), nullable=False, default='unknown')
    registry_agent_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('agents.id'),
        nullable=True,
    )
    mesh_registration_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('mesh_registrations.id'),
        nullable=True,
    )
    capabilities = db.Column(JSON, nullable=True)
    first_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    disappeared_at = db.Column(db.DateTime(timezone=True), nullable=True)
    metadata_ = db.Column('metadata', JSON, nullable=True)

    host = db.relationship('DiscoveredHost', backref='agents')
    registry_agent = db.relationship('Agent', backref='discovered_agents')
    mesh_registration = db.relationship('MeshRegistration', backref='discovered_agents')

    @property
    def host_address(self):
        return self.host.address if self.host else None

    @property
    def host_port(self):
        return self.host.port if self.host else None

    __table_args__ = (
        Index('ix_discovered_agents_tenant', 'tenant_id'),
        Index('ix_discovered_agents_governance', 'governance_status'),
        Index('ix_discovered_agents_registry', 'registry_agent_id'),
        Index('ix_discovered_agents_host', 'host_id'),
    )

    def __repr__(self):
        return f'<DiscoveredAgent {self.name} [{self.governance_status}]>'


class DiscoveredTool(db.Model):
    """An MCP tool discovered on a host."""

    __tablename__ = 'discovered_tools'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('discovered_hosts.id'),
        nullable=False,
    )
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    tool_name = db.Column(db.String(255), nullable=False)
    tool_description = db.Column(db.Text, nullable=True)
    input_schema = db.Column(JSON, nullable=True)
    mcp_server_url = db.Column(db.String(2048), nullable=True)
    governance_status = db.Column(db.String(30), nullable=False, default='ungoverned')
    mesh_tool_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('mesh_tools.id'),
        nullable=True,
    )
    first_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metadata_ = db.Column('metadata', JSON, nullable=True)

    host = db.relationship('DiscoveredHost', backref='tools')

    __table_args__ = (
        Index('ix_discovered_tools_tenant', 'tenant_id'),
        Index('ix_discovered_tools_governance', 'governance_status'),
        Index('ix_discovered_tools_host', 'host_id'),
    )

    def __repr__(self):
        return f'<DiscoveredTool {self.tool_name} [{self.governance_status}]>'


class DiscoveryScanSchedule(db.Model):
    """A recurring schedule for discovery scans."""

    __tablename__ = 'discovery_scan_schedules'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    name = db.Column(db.String(255), nullable=False)
    scan_type = db.Column(db.String(30), nullable=False, default='network')
    scan_config = db.Column(JSON, nullable=False)
    cron_expression = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_run_at = db.Column(db.DateTime(timezone=True), nullable=True)
    next_run_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index('ix_discovery_scan_schedules_tenant', 'tenant_id'),
        Index('ix_discovery_scan_schedules_enabled', 'enabled'),
    )

    def __repr__(self):
        return f'<DiscoveryScanSchedule {self.name} enabled={self.enabled}>'
