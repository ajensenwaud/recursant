"""Marshmallow schemas for network discovery endpoints."""

import re

from marshmallow import Schema, fields, validate, validates, ValidationError


# CIDR notation pattern
CIDR_PATTERN = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$'


# ---------------------------------------------------------------------------
# Scan configuration (nested)
# ---------------------------------------------------------------------------

class ScanConfigSchema(Schema):
    """Schema for scan configuration options."""
    cidrs = fields.List(fields.String(), load_default=None)
    hosts = fields.List(fields.String(), load_default=None)
    ports = fields.List(
        fields.Integer(),
        load_default=[5000, 8080, 8443, 9901],
    )
    port_range_start = fields.Integer(load_default=None, allow_none=True)
    port_range_end = fields.Integer(load_default=None, allow_none=True)
    k8s_namespaces = fields.List(fields.String(), load_default=None)
    k8s_labels = fields.Dict(load_default=None, allow_none=True)
    timeout_ms = fields.Integer(
        load_default=5000,
        validate=validate.Range(min=100, max=60000),
    )
    max_concurrent_probes = fields.Integer(
        load_default=50,
        validate=validate.Range(min=1, max=500),
    )
    probe_delay_ms = fields.Integer(
        load_default=0,
        validate=validate.Range(min=0, max=5000),
    )
    auth = fields.Dict(load_default=None, allow_none=True)
    tls_verify = fields.Boolean(load_default=True)

    @validates('cidrs')
    def validate_cidrs(self, value):
        """Validate CIDR notation for each entry."""
        if value is None:
            return
        for cidr in value:
            if not re.match(CIDR_PATTERN, cidr):
                raise ValidationError(
                    f'Invalid CIDR notation: {cidr}. '
                    'Expected format: x.x.x.x/n'
                )

    @validates('ports')
    def validate_ports(self, value):
        """Validate port numbers are in valid range."""
        if value is None:
            return
        for port in value:
            if port < 1 or port > 65535:
                raise ValidationError(
                    f'Port {port} out of range. Must be between 1 and 65535.'
                )


# ---------------------------------------------------------------------------
# Discovery scan schemas
# ---------------------------------------------------------------------------

class DiscoveryScanCreateSchema(Schema):
    """Schema for creating a new discovery scan."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    scan_type = fields.String(
        required=True,
        validate=validate.OneOf(['network', 'kubernetes', 'dns']),
    )
    config = fields.Nested(ScanConfigSchema, required=True)


class DiscoveryScanSchema(Schema):
    """Schema for full discovery scan representation."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String(dump_only=True)
    name = fields.String()
    status = fields.String()
    scan_type = fields.String()
    config = fields.Dict()
    summary = fields.Dict(dump_only=True)
    started_at = fields.DateTime(dump_only=True)
    completed_at = fields.DateTime(dump_only=True)
    created_by = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class DiscoveryScanListSchema(Schema):
    """Schema for lightweight scan list views."""
    id = fields.UUID(dump_only=True)
    name = fields.String(dump_only=True)
    status = fields.String(dump_only=True)
    scan_type = fields.String(dump_only=True)
    summary = fields.Dict(dump_only=True)
    started_at = fields.DateTime(dump_only=True)
    completed_at = fields.DateTime(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


# ---------------------------------------------------------------------------
# Discovered host schemas
# ---------------------------------------------------------------------------

class DiscoveredHostSchema(Schema):
    """Schema for full discovered host representation."""
    id = fields.UUID(dump_only=True)
    scan_id = fields.UUID(dump_only=True)
    address = fields.String()
    port = fields.Integer()
    protocol = fields.String()
    service_type = fields.String()
    tls_info = fields.Dict()
    first_seen_at = fields.DateTime(dump_only=True)
    last_seen_at = fields.DateTime(dump_only=True)
    status = fields.String()
    metadata = fields.Dict(attribute='metadata_')


# ---------------------------------------------------------------------------
# Discovered agent schemas
# ---------------------------------------------------------------------------

class DiscoveredAgentSchema(Schema):
    """Schema for full discovered agent representation."""
    id = fields.UUID(dump_only=True)
    host_id = fields.UUID(dump_only=True)
    agent_card = fields.Dict()
    name = fields.String()
    description = fields.String()
    version = fields.String()
    framework_type = fields.String()
    governance_status = fields.String()
    registry_agent_id = fields.UUID(dump_only=True, allow_none=True)
    mesh_registration_id = fields.UUID(dump_only=True, allow_none=True)
    capabilities = fields.List(fields.Dict())
    first_seen_at = fields.DateTime(dump_only=True)
    last_seen_at = fields.DateTime(dump_only=True)
    disappeared_at = fields.DateTime(dump_only=True, allow_none=True)
    host = fields.Nested(DiscoveredHostSchema, dump_only=True)


class DiscoveredAgentListSchema(Schema):
    """Schema for lightweight discovered agent list views."""
    id = fields.UUID(dump_only=True)
    name = fields.String(dump_only=True)
    version = fields.String(dump_only=True)
    framework_type = fields.String(dump_only=True)
    governance_status = fields.String(dump_only=True)
    first_seen_at = fields.DateTime(dump_only=True)
    last_seen_at = fields.DateTime(dump_only=True)
    disappeared_at = fields.DateTime(dump_only=True, allow_none=True)
    host_address = fields.String(dump_only=True)
    host_port = fields.Integer(dump_only=True)


# ---------------------------------------------------------------------------
# Discovered tool schemas
# ---------------------------------------------------------------------------

class DiscoveredToolSchema(Schema):
    """Schema for full discovered tool representation."""
    id = fields.UUID(dump_only=True)
    host_id = fields.UUID(dump_only=True)
    tool_name = fields.String()
    tool_description = fields.String()
    input_schema = fields.Dict()
    mcp_server_url = fields.String()
    governance_status = fields.String()
    mesh_tool_id = fields.UUID(dump_only=True, allow_none=True)
    first_seen_at = fields.DateTime(dump_only=True)
    last_seen_at = fields.DateTime(dump_only=True)


class DiscoveredToolListSchema(Schema):
    """Schema for lightweight discovered tool list views."""
    id = fields.UUID(dump_only=True)
    tool_name = fields.String(dump_only=True)
    tool_description = fields.String(dump_only=True)
    input_schema = fields.Dict(dump_only=True)
    governance_status = fields.String(dump_only=True)
    mcp_server_url = fields.String(dump_only=True)
    first_seen_at = fields.DateTime(dump_only=True)
    last_seen_at = fields.DateTime(dump_only=True)


# ---------------------------------------------------------------------------
# Onboarding schemas
# ---------------------------------------------------------------------------

class OnboardAgentSchema(Schema):
    """Schema for onboarding a discovered agent into the registry."""
    auto_submit = fields.Boolean(load_default=False)
    risk_tier = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(['low', 'medium', 'high', 'critical']),
    )
    classification = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(['internal', 'confidential', 'restricted', 'public']),
    )
    data_sensitivity = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(['none', 'pii', 'phi', 'financial', 'secret']),
    )
    owner_id = fields.String(load_default=None, allow_none=True)
    team_id = fields.String(load_default=None, allow_none=True)
    contact_email = fields.String(load_default=None, allow_none=True)
    guardrail_profile_id = fields.UUID(load_default=None, allow_none=True)


class BulkOnboardSchema(Schema):
    """Schema for bulk onboarding multiple discovered agents."""
    agent_ids = fields.List(
        fields.UUID(),
        required=True,
        validate=validate.Length(min=1, max=50),
    )
    auto_submit = fields.Boolean(load_default=False)
    risk_tier = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(['low', 'medium', 'high', 'critical']),
    )
    classification = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(['internal', 'confidential', 'restricted', 'public']),
    )
    data_sensitivity = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(['none', 'pii', 'phi', 'financial', 'secret']),
    )


class OnboardToolSchema(Schema):
    """Schema for onboarding a discovered tool into the mesh."""
    pass


# ---------------------------------------------------------------------------
# Schedule schemas
# ---------------------------------------------------------------------------

class DiscoveryScanScheduleSchema(Schema):
    """Schema for full scan schedule representation."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    scan_type = fields.String(dump_only=True)
    scan_config = fields.Nested(ScanConfigSchema, required=True)
    cron_expression = fields.String(required=True, validate=validate.Length(min=1, max=100))
    enabled = fields.Boolean(load_default=True)
    last_run_at = fields.DateTime(dump_only=True, allow_none=True)
    next_run_at = fields.DateTime(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)


class DiscoveryScanScheduleCreateSchema(Schema):
    """Schema for creating a scan schedule."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    scan_config = fields.Nested(ScanConfigSchema, required=True)
    scan_type = fields.String(
        required=True,
        validate=validate.OneOf(['network', 'kubernetes', 'dns']),
    )
    cron_expression = fields.String(required=True, validate=validate.Length(min=1, max=100))
    enabled = fields.Boolean(load_default=True)


# ---------------------------------------------------------------------------
# Stats schema
# ---------------------------------------------------------------------------

class DiscoveryStatsSchema(Schema):
    """Schema for discovery statistics overview."""
    total_hosts = fields.Integer()
    total_agents = fields.Integer()
    total_tools = fields.Integer()
    governed_agents = fields.Integer()
    ungoverned_agents = fields.Integer()
    onboarded_agents = fields.Integer()
    quarantined_agents = fields.Integer()
    dismissed_agents = fields.Integer()
    governed_tools = fields.Integer()
    ungoverned_tools = fields.Integer()
    governance_coverage_pct = fields.Float()
