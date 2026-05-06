from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (
    Agent,
    AgentVersion,
    Capability,
    ToolDependency,
    AgentRelationship,
    GuardrailProfile,
    AgentStatus,
    Classification,
    DataSensitivity,
    RiskTier,
    EndpointType,
    AuthMethod,
)
from app.schemas import AgentSchema


class AgentServiceError(Exception):
    """Base exception for agent service errors."""
    pass


class AgentNotFoundError(AgentServiceError):
    """Raised when an agent is not found."""
    pass


class AgentValidationError(AgentServiceError):
    """Raised when agent validation fails."""
    pass


class DuplicateAgentError(AgentServiceError):
    """Raised when an agent with the same name already exists."""
    pass


class GuardrailProfileError(AgentServiceError):
    """Raised when guardrail profile validation fails."""
    pass


class AgentService:
    """Service for managing agents."""

    @staticmethod
    def create_agent(data: dict, created_by: str) -> Agent:
        """
        Create a new agent.

        REQ-SUB-001: All required fields must be populated (validated by schema)
        REQ-SUB-002: Agent name must be unique within tenant namespace
        REQ-SUB-003: Version must follow semantic versioning (validated by schema)
        REQ-SUB-006: At least one capability must be defined (validated by schema)
        REQ-SUB-007: Guardrail profile must exist and be active
        """
        tenant_id = data.get('tenant_id', 'default')

        # REQ-SUB-002: Check for duplicate name within tenant
        existing = Agent.query.filter(
            and_(
                Agent.tenant_id == tenant_id,
                Agent.name == data['name'],
                Agent.deleted_at.is_(None)
            )
        ).first()

        if existing:
            raise DuplicateAgentError(
                f"Agent with name '{data['name']}' already exists in tenant '{tenant_id}' (REQ-SUB-002)"
            )

        # REQ-SUB-007: Validate guardrail profile if provided
        guardrail_profile_id = data.get('guardrail_profile_id')
        if guardrail_profile_id:
            profile = db.session.get(GuardrailProfile, guardrail_profile_id)
            if not profile:
                raise GuardrailProfileError(
                    f"Guardrail profile '{guardrail_profile_id}' not found (REQ-SUB-007)"
                )
            if not profile.is_active:
                raise GuardrailProfileError(
                    f"Guardrail profile '{guardrail_profile_id}' is not active (REQ-SUB-007)"
                )

        # Extract endpoint data
        endpoint = data['endpoint']

        # Extract resource quota
        resource_quota = data.get('resource_quota') or {}

        # Create the agent
        agent = Agent(
            name=data['name'],
            version=data['version'],
            description=data['description'],
            owner_id=data['owner_id'],
            team_id=data['team_id'],
            contact_email=data['contact_email'],
            tenant_id=tenant_id,
            classification=Classification(data['classification']),
            data_sensitivity=DataSensitivity(data['data_sensitivity']),
            risk_tier=RiskTier(data['risk_tier']),
            status=AgentStatus.DRAFT,
            endpoint_type=EndpointType(endpoint['type']),
            endpoint_url=endpoint['url'],
            endpoint_auth_method=AuthMethod(endpoint['auth_method']),
            endpoint_timeout_ms=endpoint.get('timeout_ms', 30000),
            endpoint_agent_protocol=endpoint.get('agent_protocol', 'A2A'),
            guardrail_profile_id=guardrail_profile_id,
            execution_graph_id=data.get('execution_graph_id'),
            max_tokens_per_request=resource_quota.get('max_tokens_per_request'),
            max_requests_per_minute=resource_quota.get('max_requests_per_minute'),
            max_cost_per_day_usd=resource_quota.get('max_cost_per_day_usd'),
        )

        db.session.add(agent)

        # Add capabilities
        for cap_data in data['capabilities']:
            capability = Capability(
                agent=agent,
                name=cap_data['name'],
                description=cap_data['description'],
                input_schema=cap_data.get('input_schema'),
                output_schema=cap_data.get('output_schema'),
            )
            db.session.add(capability)

        # Add tool dependencies
        for tool_data in data.get('tools', []):
            tool_dep = ToolDependency(
                agent=agent,
                tool_id=tool_data['tool_id'],
                required=tool_data.get('required', True),
            )
            db.session.add(tool_dep)

        # Add agent relationships
        for upstream in data.get('upstream_agents', []):
            rel = AgentRelationship(
                agent=agent,
                related_agent_id=upstream['agent_id'],
                relationship_type='upstream',
            )
            db.session.add(rel)

        for downstream in data.get('downstream_agents', []):
            rel = AgentRelationship(
                agent=agent,
                related_agent_id=downstream['agent_id'],
                relationship_type='downstream',
            )
            db.session.add(rel)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if 'uq_tenant_agent_name' in str(e):
                raise DuplicateAgentError(
                    f"Agent with name '{data['name']}' already exists in tenant '{tenant_id}'"
                )
            raise AgentServiceError(f"Database error: {str(e)}")

        # Create initial version snapshot
        AgentService._create_version_snapshot(agent, created_by)

        return agent

    @staticmethod
    def get_agent(agent_id: UUID, include_deleted: bool = False) -> Agent:
        """Get an agent by ID."""
        query = Agent.query.filter(Agent.id == agent_id)

        if not include_deleted:
            query = query.filter(Agent.deleted_at.is_(None))

        agent = query.first()
        if not agent:
            raise AgentNotFoundError(f"Agent with id '{agent_id}' not found")

        return agent

    @staticmethod
    def update_agent(agent_id: UUID, data: dict, updated_by: str) -> Agent:
        """
        Update an existing agent.

        Updates trigger re-evaluation and create a new version snapshot.
        """
        agent = AgentService.get_agent(agent_id)

        # Check if version is being updated
        new_version = data.get('version')
        version_changed = new_version and new_version != agent.version

        # Update basic fields
        if 'description' in data:
            agent.description = data['description']
        if 'owner_id' in data:
            agent.owner_id = data['owner_id']
        if 'team_id' in data:
            agent.team_id = data['team_id']
        if 'contact_email' in data:
            agent.contact_email = data['contact_email']
        if 'classification' in data:
            agent.classification = Classification(data['classification'])
        if 'data_sensitivity' in data:
            agent.data_sensitivity = DataSensitivity(data['data_sensitivity'])
        if 'risk_tier' in data:
            agent.risk_tier = RiskTier(data['risk_tier'])

        # Update version if provided
        if version_changed:
            agent.version = new_version

        # Update endpoint configuration
        if 'endpoint' in data:
            endpoint = data['endpoint']
            if 'type' in endpoint:
                agent.endpoint_type = EndpointType(endpoint['type'])
            if 'url' in endpoint:
                agent.endpoint_url = endpoint['url']
            if 'auth_method' in endpoint:
                agent.endpoint_auth_method = AuthMethod(endpoint['auth_method'])
            if 'timeout_ms' in endpoint:
                agent.endpoint_timeout_ms = endpoint['timeout_ms']
            if 'agent_protocol' in endpoint:
                agent.endpoint_agent_protocol = endpoint['agent_protocol']

        # Update governance
        if 'guardrail_profile_id' in data:
            guardrail_profile_id = data['guardrail_profile_id']
            if guardrail_profile_id:
                profile = db.session.get(GuardrailProfile, guardrail_profile_id)
                if not profile:
                    raise GuardrailProfileError(
                        f"Guardrail profile '{guardrail_profile_id}' not found (REQ-SUB-007)"
                    )
                if not profile.is_active:
                    raise GuardrailProfileError(
                        f"Guardrail profile '{guardrail_profile_id}' is not active (REQ-SUB-007)"
                    )
            agent.guardrail_profile_id = guardrail_profile_id

        if 'execution_graph_id' in data:
            agent.execution_graph_id = data['execution_graph_id']

        # Update resource quota
        if 'resource_quota' in data:
            quota = data['resource_quota'] or {}
            agent.max_tokens_per_request = quota.get('max_tokens_per_request')
            agent.max_requests_per_minute = quota.get('max_requests_per_minute')
            agent.max_cost_per_day_usd = quota.get('max_cost_per_day_usd')

        # Update capabilities if provided
        if 'capabilities' in data:
            # Remove existing capabilities
            Capability.query.filter(Capability.agent_id == agent.id).delete()

            # Add new capabilities
            for cap_data in data['capabilities']:
                capability = Capability(
                    agent=agent,
                    name=cap_data['name'],
                    description=cap_data['description'],
                    input_schema=cap_data.get('input_schema'),
                    output_schema=cap_data.get('output_schema'),
                )
                db.session.add(capability)

        # Update tool dependencies if provided
        if 'tools' in data:
            ToolDependency.query.filter(ToolDependency.agent_id == agent.id).delete()

            for tool_data in data['tools']:
                tool_dep = ToolDependency(
                    agent=agent,
                    tool_id=tool_data['tool_id'],
                    required=tool_data.get('required', True),
                )
                db.session.add(tool_dep)

        # Update relationships if provided
        if 'upstream_agents' in data or 'downstream_agents' in data:
            AgentRelationship.query.filter(AgentRelationship.agent_id == agent.id).delete()

            if 'upstream_agents' in data:
                for upstream in data['upstream_agents']:
                    rel = AgentRelationship(
                        agent=agent,
                        related_agent_id=upstream['agent_id'],
                        relationship_type='upstream',
                    )
                    db.session.add(rel)

            if 'downstream_agents' in data:
                for downstream in data['downstream_agents']:
                    rel = AgentRelationship(
                        agent=agent,
                        related_agent_id=downstream['agent_id'],
                        relationship_type='downstream',
                    )
                    db.session.add(rel)

        # If significant changes, reset to DRAFT status to trigger re-evaluation
        if version_changed or 'capabilities' in data or 'endpoint' in data:
            agent.status = AgentStatus.DRAFT

        agent.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise AgentServiceError(f"Database error: {str(e)}")

        # Create version snapshot if version changed
        if version_changed:
            AgentService._create_version_snapshot(agent, updated_by)

        return agent

    @staticmethod
    def delete_agent(agent_id: UUID) -> Agent:
        """
        Soft delete an agent (decommission).

        Agents are never hard-deleted for audit purposes.
        """
        agent = AgentService.get_agent(agent_id)
        agent.soft_delete()

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise AgentServiceError(f"Database error: {str(e)}")

        return agent

    @staticmethod
    def list_agents(
        tenant_id: str = 'default',
        status: Optional[AgentStatus] = None,
        team_id: Optional[str] = None,
        include_deleted: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple:
        """List agents with filtering and pagination."""
        query = Agent.query.filter(Agent.tenant_id == tenant_id)

        if not include_deleted:
            query = query.filter(Agent.deleted_at.is_(None))

        if status:
            query = query.filter(Agent.status == status)

        if team_id:
            query = query.filter(Agent.team_id == team_id)

        query = query.order_by(Agent.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    @staticmethod
    def get_agent_versions(agent_id: UUID) -> list:
        """Get all versions of an agent."""
        agent = AgentService.get_agent(agent_id, include_deleted=True)

        versions = AgentVersion.query.filter(
            AgentVersion.agent_id == agent_id
        ).order_by(AgentVersion.created_at.desc()).all()

        return versions

    @staticmethod
    def get_agent_version(agent_id: UUID, version: str) -> AgentVersion:
        """Get a specific version of an agent."""
        agent = AgentService.get_agent(agent_id, include_deleted=True)

        version_record = AgentVersion.query.filter(
            and_(
                AgentVersion.agent_id == agent_id,
                AgentVersion.version == version
            )
        ).first()

        if not version_record:
            raise AgentNotFoundError(
                f"Version '{version}' not found for agent '{agent_id}'"
            )

        return version_record

    @staticmethod
    def _create_version_snapshot(agent: Agent, created_by: str) -> AgentVersion:
        """Create a snapshot of the current agent state."""
        schema = AgentSchema()
        snapshot = schema.dump(agent)

        version_record = AgentVersion(
            agent_id=agent.id,
            version=agent.version,
            snapshot=snapshot,
            created_by=created_by,
        )

        db.session.add(version_record)
        db.session.commit()

        return version_record

    @staticmethod
    def submit_agent(agent_id: UUID) -> Agent:
        """
        Submit an agent for review.

        Transitions agent from DRAFT to SUBMITTED status, then automatically
        triggers a security scan.
        """
        agent = AgentService.get_agent(agent_id)

        if agent.status != AgentStatus.DRAFT:
            raise AgentValidationError(
                f"Agent must be in DRAFT status to submit. Current status: {agent.status.value}"
            )

        agent.status = AgentStatus.SUBMITTED
        agent.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        # Auto-trigger and execute security scan
        from app.services.security_service import SecurityService
        try:
            scan = SecurityService.trigger_scan(
                agent_id=agent_id,
                triggered_by='automatic',
                initiated_by='system',
            )
            SecurityService.execute_scan(scan.id)
        except Exception:
            # If scan trigger/execution fails, continue - agent is still submitted
            # The scan can be triggered manually later
            pass

        # Refresh agent to get updated status
        db.session.refresh(agent)

        return agent
