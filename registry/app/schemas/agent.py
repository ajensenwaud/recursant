import re
from marshmallow import Schema, fields, validate, validates, validates_schema, ValidationError, post_load, pre_load

from app.models import (
    AgentStatus,
    Classification,
    DataSensitivity,
    RiskTier,
    EndpointType,
    AuthMethod,
)


# Semantic version regex pattern
SEMVER_PATTERN = r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'

# URL pattern that allows both regular URLs and internal/Docker hostnames
# Matches: http(s)://hostname(:port)(/path)
URL_PATTERN = r'^https?://[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?(:\d+)?(/.*)?$'


def validate_endpoint_url(value):
    """Validate endpoint URL, allowing internal hostnames for Docker/K8s environments."""
    if not re.match(URL_PATTERN, value):
        raise ValidationError('Not a valid URL.')
    return value


class CapabilitySchema(Schema):
    """Schema for agent capabilities."""
    id = fields.UUID(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(required=True, validate=validate.Length(min=1))
    input_schema = fields.Dict(allow_none=True)
    output_schema = fields.Dict(allow_none=True)


class ToolDependencySchema(Schema):
    """Schema for tool dependencies."""
    tool_id = fields.String(required=True, validate=validate.Length(min=1, max=255))
    required = fields.Boolean(load_default=True)


class AgentRelationshipSchema(Schema):
    """Schema for agent relationships."""
    agent_id = fields.UUID(required=True)


class ResourceQuotaSchema(Schema):
    """Schema for resource quota configuration."""
    max_tokens_per_request = fields.Integer(validate=validate.Range(min=1), allow_none=True)
    max_requests_per_minute = fields.Integer(validate=validate.Range(min=1), allow_none=True)
    max_cost_per_day_usd = fields.Decimal(places=2, validate=validate.Range(min=0), allow_none=True)


class EndpointSchema(Schema):
    """Schema for endpoint configuration."""
    type = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in EndpointType])
    )
    url = fields.String(
        required=True,
        validate=[validate.Length(max=2048), validate_endpoint_url]
    )
    auth_method = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in AuthMethod])
    )
    timeout_ms = fields.Integer(load_default=30000, validate=validate.Range(min=100, max=300000))
    agent_protocol = fields.String(load_default='A2A', validate=validate.Length(max=50))


class AgentBaseSchema(Schema):
    """Base schema with common agent fields."""
    # Identity
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    version = fields.String(required=True, validate=validate.Length(max=50))
    description = fields.String(required=True, validate=validate.Length(min=1))

    # Ownership
    owner_id = fields.String(required=True, validate=validate.Length(min=1, max=255))
    team_id = fields.String(required=True, validate=validate.Length(min=1, max=255))
    contact_email = fields.Email(required=True)

    # Classification
    classification = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in Classification])
    )
    data_sensitivity = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in DataSensitivity])
    )
    risk_tier = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in RiskTier])
    )

    # Capabilities
    capabilities = fields.List(
        fields.Nested(CapabilitySchema),
        required=True,
        validate=validate.Length(min=1)  # REQ-SUB-006
    )

    # Technical Configuration
    endpoint = fields.Nested(EndpointSchema, required=True)

    # Dependencies
    tools = fields.List(fields.Nested(ToolDependencySchema), load_default=[])
    upstream_agents = fields.List(fields.Nested(AgentRelationshipSchema), load_default=[])
    downstream_agents = fields.List(fields.Nested(AgentRelationshipSchema), load_default=[])

    # Governance
    guardrail_profile_id = fields.String(allow_none=True, validate=validate.Length(max=255))
    execution_graph_id = fields.String(allow_none=True, validate=validate.Length(max=255))

    # Resource quota
    resource_quota = fields.Nested(ResourceQuotaSchema, allow_none=True)

    @validates('version')
    def validate_version(self, value):
        """REQ-SUB-003: Version must follow semantic versioning."""
        if not re.match(SEMVER_PATTERN, value):
            raise ValidationError(
                'Version must follow semantic versioning format (MAJOR.MINOR.PATCH). '
                f'Got: {value}'
            )

    @validates('capabilities')
    def validate_capabilities(self, value):
        """REQ-SUB-006: At least one capability must be defined."""
        if not value or len(value) == 0:
            raise ValidationError('At least one capability must be defined (REQ-SUB-006)')


class AgentCreateSchema(AgentBaseSchema):
    """Schema for creating a new agent."""
    # tenant_id can be provided or will be extracted from auth context
    tenant_id = fields.String(load_default='default', validate=validate.Length(max=255))


class AgentUpdateSchema(Schema):
    """Schema for updating an existing agent.

    All fields are optional - only provided fields will be updated.
    """
    # Identity (name cannot be changed)
    version = fields.String(validate=validate.Length(max=50))
    description = fields.String(validate=validate.Length(min=1))

    # Ownership
    owner_id = fields.String(validate=validate.Length(min=1, max=255))
    team_id = fields.String(validate=validate.Length(min=1, max=255))
    contact_email = fields.Email()

    # Classification
    classification = fields.String(
        validate=validate.OneOf([e.value for e in Classification])
    )
    data_sensitivity = fields.String(
        validate=validate.OneOf([e.value for e in DataSensitivity])
    )
    risk_tier = fields.String(
        validate=validate.OneOf([e.value for e in RiskTier])
    )

    # Capabilities
    capabilities = fields.List(
        fields.Nested(CapabilitySchema),
        validate=validate.Length(min=1)
    )

    # Technical Configuration
    endpoint = fields.Nested(EndpointSchema)

    # Dependencies
    tools = fields.List(fields.Nested(ToolDependencySchema))
    upstream_agents = fields.List(fields.Nested(AgentRelationshipSchema))
    downstream_agents = fields.List(fields.Nested(AgentRelationshipSchema))

    # Governance
    guardrail_profile_id = fields.String(allow_none=True, validate=validate.Length(max=255))
    execution_graph_id = fields.String(allow_none=True, validate=validate.Length(max=255))

    # Resource quota
    resource_quota = fields.Nested(ResourceQuotaSchema, allow_none=True)

    @validates('version')
    def validate_version(self, value):
        """REQ-SUB-003: Version must follow semantic versioning."""
        if value and not re.match(SEMVER_PATTERN, value):
            raise ValidationError(
                'Version must follow semantic versioning format (MAJOR.MINOR.PATCH). '
                f'Got: {value}'
            )


class AgentSchema(Schema):
    """Schema for agent response."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    version = fields.String()
    description = fields.String()

    # Ownership
    owner_id = fields.String()
    team_id = fields.String()
    contact_email = fields.Email()
    tenant_id = fields.String()

    # Classification
    classification = fields.Method('get_classification')
    data_sensitivity = fields.Method('get_data_sensitivity')
    risk_tier = fields.Method('get_risk_tier')

    # Status
    status = fields.Method('get_status')

    # Capabilities
    capabilities = fields.List(fields.Nested(CapabilitySchema))

    # Technical Configuration - flattened to endpoint object
    endpoint = fields.Method('get_endpoint')

    # Dependencies
    tools = fields.Method('get_tools')
    upstream_agents = fields.Method('get_upstream_agents')
    downstream_agents = fields.Method('get_downstream_agents')

    # Governance
    guardrail_profile_id = fields.String()
    execution_graph_id = fields.String()

    # Resource quota
    resource_quota = fields.Method('get_resource_quota')

    # Audit
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_classification(self, obj):
        return obj.classification.value if obj.classification else None

    def get_data_sensitivity(self, obj):
        return obj.data_sensitivity.value if obj.data_sensitivity else None

    def get_risk_tier(self, obj):
        return obj.risk_tier.value if obj.risk_tier else None

    def get_status(self, obj):
        return obj.status.value if obj.status else None

    def get_endpoint(self, obj):
        return {
            'type': obj.endpoint_type.value if obj.endpoint_type else None,
            'url': obj.endpoint_url,
            'auth_method': obj.endpoint_auth_method.value if obj.endpoint_auth_method else None,
            'timeout_ms': obj.endpoint_timeout_ms,
            'agent_protocol': obj.endpoint_agent_protocol,
        }

    def get_tools(self, obj):
        return [
            {'tool_id': t.tool_id, 'required': t.required}
            for t in obj.tool_dependencies
        ]

    def get_upstream_agents(self, obj):
        return [
            {'agent_id': str(r.related_agent_id)}
            for r in obj.relationships if r.relationship_type == 'upstream'
        ]

    def get_downstream_agents(self, obj):
        return [
            {'agent_id': str(r.related_agent_id)}
            for r in obj.relationships if r.relationship_type == 'downstream'
        ]

    def get_resource_quota(self, obj):
        if not any([obj.max_tokens_per_request, obj.max_requests_per_minute, obj.max_cost_per_day_usd]):
            return None
        return {
            'max_tokens_per_request': obj.max_tokens_per_request,
            'max_requests_per_minute': obj.max_requests_per_minute,
            'max_cost_per_day_usd': float(obj.max_cost_per_day_usd) if obj.max_cost_per_day_usd else None,
        }


class AgentVersionSchema(Schema):
    """Schema for agent version response."""
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID()
    version = fields.String()
    snapshot = fields.Dict()
    created_at = fields.DateTime()
    created_by = fields.String()


class AgentListSchema(Schema):
    """Schema for listing agents."""
    id = fields.UUID()
    name = fields.String()
    version = fields.String()
    description = fields.String()
    status = fields.Method('get_status')
    classification = fields.Method('get_classification')
    risk_tier = fields.Method('get_risk_tier')
    team_id = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_status(self, obj):
        return obj.status.value if obj.status else None

    def get_classification(self, obj):
        return obj.classification.value if obj.classification else None

    def get_risk_tier(self, obj):
        return obj.risk_tier.value if obj.risk_tier else None
