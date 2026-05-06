"""Marshmallow schemas for mesh control plane endpoints."""

from marshmallow import Schema, fields, validate


# ---------------------------------------------------------------------------
# Registration schemas
# ---------------------------------------------------------------------------

class MeshRegisterSchema(Schema):
    """Schema for sidecar registration request."""
    agent_id = fields.UUID(required=True)
    sidecar_url = fields.String(required=True, validate=validate.Length(min=1, max=2048))
    agent_card = fields.Dict(required=True)
    sovereignty_zone = fields.String(allow_none=True, load_default=None)


class MeshHeartbeatSchema(Schema):
    """Schema for sidecar heartbeat request."""
    agent_id = fields.UUID(required=True)


class MeshDeregisterSchema(Schema):
    """Schema for sidecar deregistration request."""
    agent_id = fields.UUID(required=True)
    sidecar_url = fields.String(load_default=None)


class MeshRegistrationSchema(Schema):
    """Schema for mesh registration response."""
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID()
    sidecar_url = fields.String()
    agent_card = fields.Dict()
    sovereignty_zone = fields.String(allow_none=True)
    tenant_id = fields.String()
    registered_at = fields.DateTime()
    last_heartbeat = fields.DateTime()
    status = fields.String()


# ---------------------------------------------------------------------------
# Discovery schemas
# ---------------------------------------------------------------------------

class MeshDiscoverAgentSchema(Schema):
    """Schema for a single discovered agent in discovery response."""
    agent_id = fields.UUID(attribute='agent_id')
    name = fields.String()
    sidecar_url = fields.String()
    skills = fields.List(fields.String())
    version = fields.String()
    status = fields.String()
    last_heartbeat = fields.DateTime()
    sovereignty_zone = fields.String(allow_none=True)
    classification = fields.String(allow_none=True)
    traffic_weight = fields.Integer(load_default=100)


# ---------------------------------------------------------------------------
# Policy schemas
# ---------------------------------------------------------------------------

class MeshPolicyCreateSchema(Schema):
    """Schema for creating a mesh policy."""
    source_agent_name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    dest_agent_name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    action = fields.String(required=True, validate=validate.OneOf(['allow', 'deny']))
    priority = fields.Integer(load_default=0)


class MeshPolicySchema(Schema):
    """Schema for mesh policy response."""
    id = fields.UUID(dump_only=True)
    source_agent_name = fields.String()
    dest_agent_name = fields.String()
    action = fields.String()
    priority = fields.Integer()
    tenant_id = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class MeshPolicyListSchema(Schema):
    """Compact policy schema for list/sidecar fetch."""
    id = fields.UUID(dump_only=True)
    source = fields.String(attribute='source_agent_name')
    destination = fields.String(attribute='dest_agent_name')
    action = fields.String()
    priority = fields.Integer()


# ---------------------------------------------------------------------------
# Audit schemas
# ---------------------------------------------------------------------------

class MeshAuditRecordSchema(Schema):
    """Schema for a single audit record submitted by a sidecar."""
    timestamp = fields.DateTime(required=True)
    source_agent_id = fields.String(allow_none=True, load_default=None)
    source_agent_name = fields.String(allow_none=True, load_default=None)
    dest_agent_id = fields.String(allow_none=True, load_default=None)
    dest_agent_name = fields.String(allow_none=True, load_default=None)
    task_id = fields.String(allow_none=True, load_default=None)
    a2a_method = fields.String(required=True)
    message_hash = fields.String(required=True, validate=validate.Length(min=1, max=64))
    direction = fields.String(required=True, validate=validate.OneOf(['inbound', 'outbound']))
    decision = fields.String(required=True)
    outcome = fields.String(required=True)
    details = fields.Raw(allow_none=True, load_default=None)  # list of dicts or dict
    sidecar_id = fields.String(allow_none=True, load_default=None)
    # Hash-chain fields
    record_hash = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=64))
    previous_record_hash = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=64))
    sequence_number = fields.Integer(allow_none=True, load_default=None)


class MeshAuditSubmitSchema(Schema):
    """Schema for batch audit record submission."""
    records = fields.List(fields.Nested(MeshAuditRecordSchema), required=True)


class MeshAuditLogSchema(Schema):
    """Schema for audit log response."""
    id = fields.UUID(dump_only=True)
    timestamp = fields.DateTime()
    source_agent_id = fields.String(allow_none=True)
    source_agent_name = fields.String(allow_none=True)
    dest_agent_id = fields.String(allow_none=True)
    dest_agent_name = fields.String(allow_none=True)
    task_id = fields.String(allow_none=True)
    a2a_method = fields.String()
    message_hash = fields.String()
    direction = fields.String()
    decision = fields.String()
    outcome = fields.String()
    details = fields.Raw(allow_none=True)
    sidecar_id = fields.String(allow_none=True)
    tenant_id = fields.String()
    created_at = fields.DateTime()
    record_hash = fields.String(allow_none=True)
    previous_record_hash = fields.String(allow_none=True)
    sequence_number = fields.Integer(allow_none=True)
    # Chain-of-thought auditing (Phase 2)
    cot_analysis = fields.Raw(allow_none=True)
    cot_risk_level = fields.String(allow_none=True)
    cot_flags = fields.Raw(allow_none=True)


# ---------------------------------------------------------------------------
# Compliance rule schemas
# ---------------------------------------------------------------------------

class MeshComplianceRuleSchema(Schema):
    """Schema for a compliance rule response."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String()
    rule_type = fields.String()
    source_value = fields.String()
    dest_value = fields.String()
    action = fields.String()
    priority = fields.Integer()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class MeshComplianceRuleCreateSchema(Schema):
    """Schema for creating a compliance rule."""
    rule_type = fields.String(required=True, validate=validate.OneOf(['sovereignty', 'classification']))
    source_value = fields.String(required=True, validate=validate.Length(min=1, max=100))
    dest_value = fields.String(required=True, validate=validate.Length(min=1, max=100))
    action = fields.String(required=True, validate=validate.OneOf(['allow', 'block']))
    priority = fields.Integer(load_default=0)


# ---------------------------------------------------------------------------
# Tool governance schemas
# ---------------------------------------------------------------------------

class MeshToolCreateSchema(Schema):
    """Schema for creating a mesh tool."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True, load_default=None)
    tool_type = fields.String(load_default='http', validate=validate.OneOf(['http']))
    endpoint_url = fields.String(required=True, validate=validate.Length(min=1, max=2048))
    http_method = fields.String(load_default='POST', validate=validate.OneOf(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']))
    parameters_schema = fields.Raw(allow_none=True, load_default=None)
    mcp_server_url = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=512))
    mcp_server_name = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=255))
    mcp_server_description = fields.String(allow_none=True, load_default=None)
    backend_services = fields.Raw(allow_none=True, load_default=None)


class MeshToolUpdateSchema(Schema):
    """Schema for updating a mesh tool."""
    description = fields.String(allow_none=True)
    endpoint_url = fields.String(validate=validate.Length(min=1, max=2048))
    http_method = fields.String(validate=validate.OneOf(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']))
    parameters_schema = fields.Raw(allow_none=True)
    mcp_server_url = fields.String(allow_none=True, validate=validate.Length(max=512))
    mcp_server_name = fields.String(allow_none=True, validate=validate.Length(max=255))
    mcp_server_description = fields.String(allow_none=True)
    backend_services = fields.Raw(allow_none=True)


class MeshToolSchema(Schema):
    """Schema for mesh tool response."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String()
    name = fields.String()
    description = fields.String(allow_none=True)
    tool_type = fields.String()
    endpoint_url = fields.String()
    http_method = fields.String()
    parameters_schema = fields.Raw(allow_none=True)
    mcp_server_url = fields.String(allow_none=True)
    mcp_server_name = fields.String(allow_none=True)
    mcp_server_description = fields.String(allow_none=True)
    backend_services = fields.Raw(allow_none=True)
    status = fields.String()
    approved_by = fields.String(allow_none=True)
    approved_at = fields.DateTime(allow_none=True)
    revoked_by = fields.String(allow_none=True)
    revoked_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class MeshToolWithAssignmentsSchema(Schema):
    """Schema for tool response with inlined assignments."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String()
    name = fields.String()
    description = fields.String(allow_none=True)
    tool_type = fields.String()
    endpoint_url = fields.String()
    http_method = fields.String()
    parameters_schema = fields.Raw(allow_none=True)
    mcp_server_url = fields.String(allow_none=True)
    mcp_server_name = fields.String(allow_none=True)
    mcp_server_description = fields.String(allow_none=True)
    backend_services = fields.Raw(allow_none=True)
    status = fields.String()
    approved_by = fields.String(allow_none=True)
    approved_at = fields.DateTime(allow_none=True)
    revoked_by = fields.String(allow_none=True)
    revoked_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
    assignments = fields.List(fields.Dict(), dump_default=[])


class MeshToolAssignmentCreateSchema(Schema):
    """Schema for creating a tool assignment."""
    tool_id = fields.UUID(required=True)
    agent_name = fields.String(required=True, validate=validate.Length(min=1, max=255))


class MeshToolAssignmentSchema(Schema):
    """Schema for tool assignment response."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String()
    tool_id = fields.UUID()
    agent_name = fields.String()
    tool_name = fields.String(dump_default=None)
    created_at = fields.DateTime()


class MeshEgressRuleCreateSchema(Schema):
    """Schema for creating an egress rule."""
    agent_name = fields.String(load_default='*', validate=validate.Length(min=1, max=255))
    url_pattern = fields.String(required=True, validate=validate.Length(min=1, max=2048))
    action = fields.String(required=True, validate=validate.OneOf(['allow', 'deny']))
    priority = fields.Integer(load_default=0)


class MeshEgressRuleSchema(Schema):
    """Schema for egress rule response."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String()
    agent_name = fields.String()
    url_pattern = fields.String()
    action = fields.String()
    priority = fields.Integer()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
