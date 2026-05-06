"""
Discovery service -- orchestrates network scans, stores results, handles onboarding.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from uuid import UUID

from sqlalchemy import and_, func

from app import db
from app.models.discovery import (
    DiscoveryScan, DiscoveredHost, DiscoveredAgent, DiscoveredTool,
    DiscoveryScanSchedule,
    DiscoveryScanStatus, DiscoveryScanType, ServiceType, HostStatus,
    GovernanceStatus, DiscoveredToolStatus,
)
from app.models.agent import Agent, AgentStatus, Capability, Classification, DataSensitivity, RiskTier, AuthMethod, EndpointType
from app.models.mesh import MeshRegistration, MeshPolicy
from app.services.network_scanner import NetworkScanner, ScanConfig, ScanResult, HostResult

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class DiscoveryServiceError(Exception):
    pass

class ScanNotFoundError(DiscoveryServiceError):
    pass

class ScanAlreadyCompletedError(DiscoveryServiceError):
    pass

class DiscoveredAgentNotFoundError(DiscoveryServiceError):
    pass

class DiscoveredToolNotFoundError(DiscoveryServiceError):
    pass

class AlreadyOnboardedError(DiscoveryServiceError):
    pass

class AlreadyGovernedError(DiscoveryServiceError):
    pass

class ScheduleNotFoundError(DiscoveryServiceError):
    pass


class DiscoveryService:
    """Service for managing network discovery scans and results."""

    # ------------------------------------------------------------------
    # Scan CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def create_scan(data: dict, tenant_id: str, created_by: str = None) -> DiscoveryScan:
        """Create a new discovery scan and start it in a background thread."""
        scan = DiscoveryScan(
            tenant_id=tenant_id,
            name=data['name'],
            scan_type=data['scan_type'],
            config=data['config'],
            status=DiscoveryScanStatus.PENDING.value,
            created_by=created_by,
        )
        db.session.add(scan)
        db.session.commit()

        # Start scan execution in background thread
        # We need the Flask app context to access the database
        from flask import current_app
        app = current_app._get_current_object()
        scan_id = scan.id

        thread = threading.Thread(
            target=DiscoveryService._run_scan_in_thread,
            args=(app, scan_id),
            daemon=True,
        )
        thread.start()

        return scan

    @staticmethod
    def _run_scan_in_thread(app, scan_id: UUID):
        """Execute scan in background thread with app context."""
        with app.app_context():
            try:
                DiscoveryService._execute_scan(scan_id)
            except Exception as e:
                logger.error(f"Scan {scan_id} failed: {e}", exc_info=True)
                try:
                    scan = db.session.get(DiscoveryScan, scan_id)
                    if scan:
                        scan.status = DiscoveryScanStatus.FAILED.value
                        scan.completed_at = datetime.now(timezone.utc)
                        scan.summary = {'error': str(e)[:1000]}
                        db.session.commit()
                except Exception:
                    db.session.rollback()

    @staticmethod
    def _execute_scan(scan_id: UUID):
        """Core scan execution logic."""
        scan = db.session.get(DiscoveryScan, scan_id)
        if not scan:
            return

        scan.status = DiscoveryScanStatus.RUNNING.value
        scan.started_at = datetime.now(timezone.utc)
        db.session.commit()

        # Build scanner config from scan.config JSON
        config_data = scan.config or {}
        scanner_config = ScanConfig(
            cidrs=config_data.get('cidrs', []),
            hosts=config_data.get('hosts', []),
            ports=config_data.get('ports', [5000, 8080, 8443, 9901]),
            port_range_start=config_data.get('port_range_start'),
            port_range_end=config_data.get('port_range_end'),
            timeout_ms=config_data.get('timeout_ms', 5000),
            max_concurrent_probes=config_data.get('max_concurrent_probes', 50),
            probe_delay_ms=config_data.get('probe_delay_ms', 0),
            auth=config_data.get('auth'),
            tls_verify=config_data.get('tls_verify', True),
        )

        # Execute the network scan
        scan_result = NetworkScanner.scan_sync(scanner_config)

        # Store results in database
        now = datetime.now(timezone.utc)

        for host_result in scan_result.hosts:
            if not host_result.reachable:
                continue

            # Upsert discovered host -- check if we've seen this address:port
            # before for this tenant
            existing_host = DiscoveredHost.query.filter(
                and_(
                    DiscoveredHost.tenant_id == scan.tenant_id,
                    DiscoveredHost.address == host_result.address,
                    DiscoveredHost.port == host_result.port,
                )
            ).first()

            if existing_host:
                host = existing_host
                host.last_seen_at = now
                host.status = HostStatus.ONLINE.value
                host.service_type = host_result.service_type
                host.protocol = host_result.protocol
                host.scan_id = scan.id  # Update to latest scan
                if host_result.tls_info:
                    host.tls_info = host_result.tls_info
                host.metadata_ = host_result.metadata
            else:
                host = DiscoveredHost(
                    scan_id=scan.id,
                    tenant_id=scan.tenant_id,
                    address=host_result.address,
                    port=host_result.port,
                    protocol=host_result.protocol,
                    service_type=host_result.service_type,
                    tls_info=host_result.tls_info,
                    first_seen_at=now,
                    last_seen_at=now,
                    status=HostStatus.ONLINE.value,
                    metadata_=host_result.metadata,
                )
                db.session.add(host)

            db.session.flush()  # Get host.id

            # Create/update discovered agent if A2A card found
            if host_result.service_type == 'a2a_agent' and host_result.agent_card:
                DiscoveryService._upsert_discovered_agent(
                    host, host_result, scan.tenant_id, now
                )

            # Create/update discovered agent for fingerprinted frameworks
            if host_result.framework_type and host_result.service_type != 'a2a_agent':
                DiscoveryService._upsert_fingerprinted_agent(
                    host, host_result, scan.tenant_id, now
                )

            # Create discovered tools if MCP tools found
            if host_result.mcp_tools:
                DiscoveryService._upsert_discovered_tools(
                    host, host_result, scan.tenant_id, now
                )

        # Mark hosts not seen in this scan as potentially offline
        # (only for hosts in the scanned CIDR ranges)
        try:
            DiscoveryService._mark_disappeared_hosts(scan, now)
        except Exception as e:
            logger.warning(f"Error marking disappeared hosts for scan {scan_id}: {e}")

        # Update scan status
        scan.status = DiscoveryScanStatus.COMPLETED.value
        scan.completed_at = datetime.now(timezone.utc)
        scan.summary = {
            'hosts_scanned': scan_result.hosts_scanned,
            'hosts_reachable': sum(1 for h in scan_result.hosts if h.reachable),
            'agents_found': scan_result.agents_found,
            'tools_found': scan_result.tools_found,
            'errors': scan_result.errors,
            'duration_ms': round(scan_result.duration_ms, 1),
        }
        db.session.commit()

    @staticmethod
    def _upsert_discovered_agent(host, host_result: HostResult, tenant_id: str, now):
        """Create or update a discovered agent from an A2A agent card."""
        card = host_result.agent_card
        agent_name = card.get('name', '')
        agent_version = card.get('version', '')

        existing = DiscoveredAgent.query.filter(
            and_(
                DiscoveredAgent.host_id == host.id,
                DiscoveredAgent.tenant_id == tenant_id,
            )
        ).first()

        # Determine governance status
        governance_status = DiscoveryService._classify_governance(
            agent_name, host.address, host.port, tenant_id
        )

        # Parse capabilities from agent card skills
        capabilities = []
        skills = card.get('skills', [])
        if isinstance(skills, list):
            for s in skills:
                if isinstance(s, dict):
                    capabilities.append({
                        'id': s.get('id', ''),
                        'name': s.get('name', ''),
                        'description': s.get('description', ''),
                        'tags': s.get('tags', []),
                    })

        if existing:
            existing.agent_card = card
            existing.name = agent_name
            existing.description = card.get('description', '')
            existing.version = agent_version
            existing.framework_type = host_result.framework_type
            existing.capabilities = capabilities
            existing.last_seen_at = now
            existing.disappeared_at = None  # Back online
            # Only update governance status if it was unknown
            if existing.governance_status == GovernanceStatus.UNKNOWN.value:
                existing.governance_status = governance_status
        else:
            agent = DiscoveredAgent(
                host_id=host.id,
                tenant_id=tenant_id,
                agent_card=card,
                name=agent_name,
                description=card.get('description', ''),
                version=agent_version,
                framework_type=host_result.framework_type,
                governance_status=governance_status,
                capabilities=capabilities,
                first_seen_at=now,
                last_seen_at=now,
            )
            # Link to existing registry agent if governed
            registry_agent = DiscoveryService._find_registry_agent(agent_name, tenant_id)
            if registry_agent:
                agent.registry_agent_id = registry_agent.id
                mesh_reg = MeshRegistration.query.filter_by(agent_id=registry_agent.id).first()
                if mesh_reg:
                    agent.mesh_registration_id = mesh_reg.id

            db.session.add(agent)

    @staticmethod
    def _upsert_fingerprinted_agent(host, host_result: HostResult, tenant_id: str, now):
        """Create a discovered agent entry for a fingerprinted (non-A2A) agent."""
        existing = DiscoveredAgent.query.filter(
            and_(
                DiscoveredAgent.host_id == host.id,
                DiscoveredAgent.tenant_id == tenant_id,
            )
        ).first()

        if existing:
            existing.framework_type = host_result.framework_type
            existing.last_seen_at = now
            existing.disappeared_at = None
        else:
            agent = DiscoveredAgent(
                host_id=host.id,
                tenant_id=tenant_id,
                name=f"unknown-{host.address}:{host.port}",
                framework_type=host_result.framework_type,
                governance_status=GovernanceStatus.UNKNOWN.value,
                first_seen_at=now,
                last_seen_at=now,
                metadata_=host_result.metadata,
            )
            db.session.add(agent)

    @staticmethod
    def _upsert_discovered_tools(host, host_result: HostResult, tenant_id: str, now):
        """Create or update discovered MCP tools."""
        from app.models.mesh import MeshTool

        mcp_server_url = f"{host_result.protocol}://{host_result.address}:{host_result.port}"

        for tool_data in host_result.mcp_tools:
            tool_name = tool_data.get('name', '')
            if not tool_name:
                continue

            existing = DiscoveredTool.query.filter(
                and_(
                    DiscoveredTool.host_id == host.id,
                    DiscoveredTool.tool_name == tool_name,
                    DiscoveredTool.tenant_id == tenant_id,
                )
            ).first()

            # Check if tool is already governed in the mesh
            governed_tool = MeshTool.query.filter(
                and_(
                    MeshTool.tenant_id == tenant_id,
                    MeshTool.name == tool_name,
                )
            ).first()

            gov_status = (
                DiscoveredToolStatus.GOVERNED.value
                if governed_tool
                else DiscoveredToolStatus.UNGOVERNED.value
            )

            if existing:
                existing.tool_description = tool_data.get('description', '')
                existing.input_schema = tool_data.get('inputSchema', {})
                existing.last_seen_at = now
                if existing.governance_status == DiscoveredToolStatus.UNGOVERNED.value:
                    existing.governance_status = gov_status
                if governed_tool:
                    existing.mesh_tool_id = governed_tool.id
            else:
                tool = DiscoveredTool(
                    host_id=host.id,
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    tool_description=tool_data.get('description', ''),
                    input_schema=tool_data.get('inputSchema', {}),
                    mcp_server_url=mcp_server_url,
                    governance_status=gov_status,
                    mesh_tool_id=governed_tool.id if governed_tool else None,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                db.session.add(tool)

    @staticmethod
    def _classify_governance(agent_name: str, address: str, port: int, tenant_id: str) -> str:
        """Classify an agent's governance status by cross-referencing with registry."""
        # Check if agent exists in registry
        registry_agent = DiscoveryService._find_registry_agent(agent_name, tenant_id)
        if not registry_agent:
            return GovernanceStatus.UNKNOWN.value

        # Check if it has an active mesh registration (sidecar)
        mesh_reg = MeshRegistration.query.filter_by(agent_id=registry_agent.id).first()
        if mesh_reg:
            return GovernanceStatus.GOVERNED.value
        else:
            return GovernanceStatus.KNOWN_UNGOVERNED.value

    @staticmethod
    def _find_registry_agent(agent_name: str, tenant_id: str) -> Optional[Agent]:
        """Find a registered agent by name."""
        return Agent.query.filter(
            and_(
                Agent.name == agent_name,
                Agent.tenant_id == tenant_id,
                Agent.deleted_at.is_(None),
            )
        ).first()

    @staticmethod
    def _mark_disappeared_hosts(scan: DiscoveryScan, now):
        """Mark agents on hosts not seen in this scan as disappeared."""
        config = scan.config or {}
        scanned_cidrs = config.get('cidrs', [])
        scanned_hosts = config.get('hosts', [])

        if not scanned_cidrs and not scanned_hosts:
            return

        # Build set of scanned host addresses (from explicit hosts list)
        scanned_addresses = set()
        for host_entry in (scanned_hosts or []):
            if ':' in host_entry:
                hostname = host_entry.rsplit(':', 1)[0]
                scanned_addresses.add(hostname)
            else:
                scanned_addresses.add(host_entry)

        # Build CIDR networks for IP-based matching
        import ipaddress as ipaddr
        networks = []
        for cidr in scanned_cidrs:
            try:
                networks.append(ipaddr.ip_network(cidr, strict=False))
            except ValueError:
                continue

        if not networks and not scanned_addresses:
            return

        # Find hosts that were previously online but weren't seen in this scan
        hosts_in_range = DiscoveredHost.query.filter(
            and_(
                DiscoveredHost.tenant_id == scan.tenant_id,
                DiscoveredHost.status == HostStatus.ONLINE.value,
                DiscoveredHost.last_seen_at < scan.started_at,
            )
        ).all()

        for host in hosts_in_range:
            in_scope = False

            # Check if host address matches any explicit hostname
            if host.address in scanned_addresses:
                in_scope = True

            # Check if host IP is in any scanned CIDR
            if not in_scope and networks:
                try:
                    host_ip = ipaddr.ip_address(host.address)
                    if any(host_ip in net for net in networks):
                        in_scope = True
                except ValueError:
                    pass

            if in_scope:
                host.status = HostStatus.OFFLINE.value
                # Mark associated agents as disappeared
                for agent in DiscoveredAgent.query.filter_by(host_id=host.id).all():
                    if agent.disappeared_at is None:
                        agent.disappeared_at = now

    # ------------------------------------------------------------------
    # Scan queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_scan(scan_id: UUID, tenant_id: str) -> DiscoveryScan:
        scan = db.session.get(DiscoveryScan, scan_id)
        if not scan or scan.tenant_id != tenant_id:
            raise ScanNotFoundError(f"Scan {scan_id} not found")
        return scan

    @staticmethod
    def list_scans(tenant_id: str, status: str = None, page: int = 1, per_page: int = 20) -> Tuple[List[DiscoveryScan], int]:
        query = DiscoveryScan.query.filter_by(tenant_id=tenant_id)
        if status:
            query = query.filter_by(status=status)
        query = query.order_by(DiscoveryScan.created_at.desc())
        total = query.count()
        scans = query.offset((page - 1) * per_page).limit(per_page).all()
        return scans, total

    @staticmethod
    def cancel_scan(scan_id: UUID, tenant_id: str) -> DiscoveryScan:
        scan = DiscoveryService.get_scan(scan_id, tenant_id)
        if scan.status in (DiscoveryScanStatus.COMPLETED.value, DiscoveryScanStatus.FAILED.value):
            raise ScanAlreadyCompletedError(f"Scan {scan_id} already {scan.status}")
        scan.status = DiscoveryScanStatus.CANCELLED.value
        scan.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return scan

    @staticmethod
    def rerun_scan(scan_id: UUID, tenant_id: str, created_by: str = None) -> DiscoveryScan:
        original = DiscoveryService.get_scan(scan_id, tenant_id)
        data = {
            'name': f"{original.name} (re-run)",
            'scan_type': original.scan_type,
            'config': original.config,
        }
        return DiscoveryService.create_scan(data, tenant_id, created_by)

    # ------------------------------------------------------------------
    # Discovered agent queries
    # ------------------------------------------------------------------

    @staticmethod
    def list_discovered_agents(
        tenant_id: str,
        governance_status: str = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[DiscoveredAgent], int]:
        query = DiscoveredAgent.query.filter_by(tenant_id=tenant_id)
        if governance_status:
            query = query.filter_by(governance_status=governance_status)
        query = query.order_by(DiscoveredAgent.last_seen_at.desc())
        total = query.count()
        agents = query.offset((page - 1) * per_page).limit(per_page).all()
        return agents, total

    @staticmethod
    def get_discovered_agent(agent_id: UUID, tenant_id: str) -> DiscoveredAgent:
        agent = db.session.get(DiscoveredAgent, agent_id)
        if not agent or agent.tenant_id != tenant_id:
            raise DiscoveredAgentNotFoundError(f"Discovered agent {agent_id} not found")
        return agent

    # ------------------------------------------------------------------
    # Discovered tool queries
    # ------------------------------------------------------------------

    @staticmethod
    def list_discovered_tools(
        tenant_id: str,
        governance_status: str = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[DiscoveredTool], int]:
        query = DiscoveredTool.query.filter_by(tenant_id=tenant_id)
        if governance_status:
            query = query.filter_by(governance_status=governance_status)
        query = query.order_by(DiscoveredTool.last_seen_at.desc())
        total = query.count()
        tools = query.offset((page - 1) * per_page).limit(per_page).all()
        return tools, total

    @staticmethod
    def get_discovered_tool(tool_id: UUID, tenant_id: str) -> DiscoveredTool:
        tool = db.session.get(DiscoveredTool, tool_id)
        if not tool or tool.tenant_id != tenant_id:
            raise DiscoveredToolNotFoundError(f"Discovered tool {tool_id} not found")
        return tool

    # ------------------------------------------------------------------
    # Onboarding
    # ------------------------------------------------------------------

    @staticmethod
    def onboard_agent(agent_id: UUID, tenant_id: str, options: dict) -> Agent:
        """
        Onboard a discovered agent into the registry.
        Creates an Agent record in DRAFT status from the discovered agent's data.
        Optionally auto-submits to trigger security scan + evaluation.
        """
        discovered = DiscoveryService.get_discovered_agent(agent_id, tenant_id)

        if discovered.governance_status == GovernanceStatus.GOVERNED.value:
            raise AlreadyGovernedError("Agent is already registered and governed")
        if discovered.governance_status == GovernanceStatus.ONBOARDED.value:
            raise AlreadyOnboardedError("Agent has already been onboarded")

        host = discovered.host

        # Map A2A card fields to Agent model
        endpoint_url = f"{host.protocol}://{host.address}:{host.port}"

        # Determine auth method from agent card
        auth_method = AuthMethod.API_KEY.value
        if discovered.agent_card:
            security = discovered.agent_card.get(
                'securitySchemes',
                discovered.agent_card.get('security_schemes', {}),
            )
            if isinstance(security, (dict, list)):
                sec_str = str(security).lower()
                if 'mtls' in sec_str or 'mutual' in sec_str:
                    auth_method = AuthMethod.MTLS.value
                elif 'oauth' in sec_str:
                    auth_method = AuthMethod.OAUTH2.value

        # Map option strings to enum members
        classification_val = Classification(options['classification']) if options.get('classification') else Classification.INTERNAL
        sensitivity_val = DataSensitivity(options['data_sensitivity']) if options.get('data_sensitivity') else DataSensitivity.NONE
        risk_val = RiskTier(options['risk_tier']) if options.get('risk_tier') else RiskTier.MEDIUM
        auth_enum = AuthMethod(auth_method) if auth_method else AuthMethod.API_KEY

        # Generate a unique agent name -- if the name already exists in the
        # registry we append the host address to disambiguate.
        base_name = discovered.name or f"discovered-{host.address}-{host.port}"
        existing = Agent.query.filter(
            and_(
                Agent.name == base_name,
                Agent.tenant_id == tenant_id,
                Agent.deleted_at.is_(None),
            )
        ).first()
        agent_name = base_name if not existing else f"{base_name} ({host.address}:{host.port})"

        # Create the Agent record
        agent = Agent(
            name=agent_name,
            version=discovered.version or '0.0.1',
            description=discovered.description or f"Auto-discovered agent at {endpoint_url}",
            owner_id=options.get('owner_id') or 'discovery-service',
            team_id=options.get('team_id') or 'unassigned',
            contact_email=options.get('contact_email') or '',
            tenant_id=tenant_id,
            classification=classification_val,
            data_sensitivity=sensitivity_val,
            risk_tier=risk_val,
            endpoint_type=EndpointType.CUSTOM,
            endpoint_url=endpoint_url,
            endpoint_auth_method=auth_enum,
            endpoint_timeout_ms=30000,
            endpoint_agent_protocol='A2A',
            status=AgentStatus.DRAFT,
        )
        db.session.add(agent)
        db.session.flush()

        # Create capabilities from discovered skills
        if discovered.capabilities:
            for cap_data in discovered.capabilities:
                if isinstance(cap_data, dict) and cap_data.get('name'):
                    cap = Capability(
                        agent_id=agent.id,
                        name=cap_data['name'],
                        description=cap_data.get('description', ''),
                    )
                    db.session.add(cap)

        # If no capabilities were found, create a default one
        caps_count = len(discovered.capabilities) if discovered.capabilities else 0
        if caps_count == 0:
            cap = Capability(
                agent_id=agent.id,
                name='default',
                description=f'Default capability for {agent.name}',
            )
            db.session.add(cap)

        # Update discovered agent status
        discovered.governance_status = GovernanceStatus.ONBOARDED.value
        discovered.registry_agent_id = agent.id

        db.session.commit()

        # Auto-submit if requested
        if options.get('auto_submit'):
            from app.services.agent_service import AgentService
            try:
                AgentService.submit_agent(agent.id, tenant_id)
            except Exception as e:
                logger.warning(f"Auto-submit failed for onboarded agent {agent.id}: {e}")

        return agent

    @staticmethod
    def bulk_onboard_agents(
        agent_ids: List[UUID],
        tenant_id: str,
        options: dict,
    ) -> List[Dict]:
        """
        Bulk onboard multiple discovered agents.
        Returns list of {agent_id, status, registry_agent_id, error} dicts.
        Each agent is onboarded in its own savepoint so one failure doesn't
        poison the session for subsequent agents.
        """
        results = []
        for agent_id in agent_ids:
            try:
                agent = DiscoveryService.onboard_agent(agent_id, tenant_id, options)
                results.append({
                    'discovered_agent_id': str(agent_id),
                    'status': 'success',
                    'registry_agent_id': str(agent.id),
                })
            except (AlreadyOnboardedError, AlreadyGovernedError) as e:
                db.session.rollback()
                results.append({
                    'discovered_agent_id': str(agent_id),
                    'status': 'conflict',
                    'error': str(e),
                })
            except Exception as e:
                db.session.rollback()
                results.append({
                    'discovered_agent_id': str(agent_id),
                    'status': 'error',
                    'error': str(e),
                })
        return results

    @staticmethod
    def onboard_tool(tool_id: UUID, tenant_id: str) -> dict:
        """Onboard a discovered MCP tool into the MeshTool table."""
        from app.models.mesh import MeshTool

        discovered = DiscoveryService.get_discovered_tool(tool_id, tenant_id)

        if discovered.governance_status == DiscoveredToolStatus.GOVERNED.value:
            raise AlreadyGovernedError("Tool is already governed")
        if discovered.governance_status == DiscoveredToolStatus.ONBOARDED.value:
            raise AlreadyOnboardedError("Tool has already been onboarded")

        tool = MeshTool(
            tenant_id=tenant_id,
            name=discovered.tool_name,
            description=discovered.tool_description or '',
            tool_type='http',
            endpoint_url=discovered.mcp_server_url or '',
            http_method='POST',
            parameters_schema=discovered.input_schema,
            mcp_server_url=discovered.mcp_server_url,
            mcp_server_name=discovered.tool_name,
            mcp_server_description=discovered.tool_description or '',
            status='submitted',
        )
        db.session.add(tool)
        db.session.flush()

        discovered.governance_status = DiscoveredToolStatus.ONBOARDED.value
        discovered.mesh_tool_id = tool.id
        db.session.commit()

        return {'tool_id': str(tool.id), 'tool_name': tool.name}

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------

    @staticmethod
    def quarantine_agent(agent_id: UUID, tenant_id: str) -> DiscoveredAgent:
        """Quarantine a discovered agent -- generates deny policies."""
        discovered = DiscoveryService.get_discovered_agent(agent_id, tenant_id)
        discovered.governance_status = GovernanceStatus.QUARANTINED.value

        # Generate deny policy: block all governed agents from talking to this agent
        agent_name = discovered.name or f"unknown-{discovered.host.address}:{discovered.host.port}"

        # Check if deny policy already exists
        existing_policy = MeshPolicy.query.filter(
            and_(
                MeshPolicy.tenant_id == tenant_id,
                MeshPolicy.source_agent_name == '*',
                MeshPolicy.dest_agent_name == agent_name,
                MeshPolicy.action == 'deny',
            )
        ).first()

        if not existing_policy:
            policy = MeshPolicy(
                tenant_id=tenant_id,
                source_agent_name='*',
                dest_agent_name=agent_name,
                action='deny',
                priority=1000,  # High priority deny
            )
            db.session.add(policy)

        db.session.commit()
        return discovered

    @staticmethod
    def dismiss_agent(agent_id: UUID, tenant_id: str) -> DiscoveredAgent:
        """Dismiss a discovered agent -- mark as intentionally ungoverned."""
        discovered = DiscoveryService.get_discovered_agent(agent_id, tenant_id)
        discovered.governance_status = GovernanceStatus.DISMISSED.value
        db.session.commit()
        return discovered

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @staticmethod
    def get_stats(tenant_id: str) -> dict:
        """Get governance coverage statistics."""
        total_hosts = DiscoveredHost.query.filter_by(tenant_id=tenant_id).count()

        agent_counts = db.session.query(
            DiscoveredAgent.governance_status,
            func.count(DiscoveredAgent.id),
        ).filter(
            DiscoveredAgent.tenant_id == tenant_id,
        ).group_by(
            DiscoveredAgent.governance_status,
        ).all()

        agent_stats = dict(agent_counts)
        total_agents = sum(agent_stats.values())

        governed = agent_stats.get(GovernanceStatus.GOVERNED.value, 0)
        onboarded = agent_stats.get(GovernanceStatus.ONBOARDED.value, 0)
        unknown = agent_stats.get(GovernanceStatus.UNKNOWN.value, 0)
        known_ungoverned = agent_stats.get(GovernanceStatus.KNOWN_UNGOVERNED.value, 0)
        quarantined = agent_stats.get(GovernanceStatus.QUARANTINED.value, 0)
        dismissed = agent_stats.get(GovernanceStatus.DISMISSED.value, 0)

        # Coverage = (governed + onboarded) / (total - dismissed)
        countable = total_agents - dismissed
        if countable > 0:
            coverage_pct = round(((governed + onboarded) / countable) * 100, 1)
        else:
            coverage_pct = 100.0

        tool_counts = db.session.query(
            DiscoveredTool.governance_status,
            func.count(DiscoveredTool.id),
        ).filter(
            DiscoveredTool.tenant_id == tenant_id,
        ).group_by(
            DiscoveredTool.governance_status,
        ).all()

        tool_stats = dict(tool_counts)
        total_tools = sum(tool_stats.values())

        return {
            'total_hosts': total_hosts,
            'total_agents': total_agents,
            'total_tools': total_tools,
            'governed_agents': governed,
            'ungoverned_agents': unknown + known_ungoverned,
            'known_ungoverned_agents': known_ungoverned,
            'unknown_agents': unknown,
            'onboarded_agents': onboarded,
            'quarantined_agents': quarantined,
            'dismissed_agents': dismissed,
            'governed_tools': tool_stats.get(DiscoveredToolStatus.GOVERNED.value, 0),
            'ungoverned_tools': tool_stats.get(DiscoveredToolStatus.UNGOVERNED.value, 0),
            'governance_coverage_pct': coverage_pct,
        }

    # ------------------------------------------------------------------
    # Topology
    # ------------------------------------------------------------------

    @staticmethod
    def get_topology(tenant_id: str, subnet: str = None, governance_status: str = None) -> dict:
        """Build network topology graph."""
        import ipaddress as ipaddr

        host_query = DiscoveredHost.query.filter_by(tenant_id=tenant_id)
        hosts = host_query.all()

        # Pre-parse the subnet filter if provided
        network = None
        if subnet:
            try:
                network = ipaddr.ip_network(subnet, strict=False)
            except ValueError:
                pass

        nodes = []
        edges = []

        for host in hosts:
            # Filter by subnet if specified
            if network:
                try:
                    if ipaddr.ip_address(host.address) not in network:
                        continue
                except ValueError:
                    continue

            node_id = f"host-{host.id}"
            nodes.append({
                'id': node_id,
                'type': 'host',
                'address': host.address,
                'port': host.port,
                'protocol': host.protocol,
                'service_type': host.service_type,
                'status': host.status,
            })

            # Add agent nodes
            agents = DiscoveredAgent.query.filter_by(host_id=host.id).all()
            for agent in agents:
                if governance_status and agent.governance_status != governance_status:
                    continue
                agent_node_id = f"agent-{agent.id}"
                nodes.append({
                    'id': agent_node_id,
                    'type': 'agent',
                    'name': agent.name,
                    'version': agent.version,
                    'framework_type': agent.framework_type,
                    'governance_status': agent.governance_status,
                })
                edges.append({
                    'source': node_id,
                    'target': agent_node_id,
                    'type': 'hosts',
                })

            # Add tool nodes
            tools = DiscoveredTool.query.filter_by(host_id=host.id).all()
            for tool in tools:
                tool_node_id = f"tool-{tool.id}"
                nodes.append({
                    'id': tool_node_id,
                    'type': 'tool',
                    'name': tool.tool_name,
                    'governance_status': tool.governance_status,
                })
                edges.append({
                    'source': node_id,
                    'target': tool_node_id,
                    'type': 'provides',
                })

        return {'nodes': nodes, 'edges': edges}

    # ------------------------------------------------------------------
    # Schedules
    # ------------------------------------------------------------------

    @staticmethod
    def create_schedule(data: dict, tenant_id: str) -> DiscoveryScanSchedule:
        """Create a recurring scan schedule."""
        schedule = DiscoveryScanSchedule(
            tenant_id=tenant_id,
            name=data['name'],
            scan_type=data.get('scan_type', 'network'),
            scan_config=data.get('scan_config', data.get('config', {})),
            cron_expression=data['cron_expression'],
            enabled=data.get('enabled', True),
        )
        db.session.add(schedule)
        db.session.commit()
        return schedule

    @staticmethod
    def list_schedules(tenant_id: str) -> List[DiscoveryScanSchedule]:
        return DiscoveryScanSchedule.query.filter_by(tenant_id=tenant_id).all()

    @staticmethod
    def get_schedule(schedule_id: UUID, tenant_id: str) -> DiscoveryScanSchedule:
        schedule = db.session.get(DiscoveryScanSchedule, schedule_id)
        if not schedule or schedule.tenant_id != tenant_id:
            raise ScheduleNotFoundError(f"Schedule {schedule_id} not found")
        return schedule

    @staticmethod
    def update_schedule(schedule_id: UUID, tenant_id: str, data: dict) -> DiscoveryScanSchedule:
        schedule = DiscoveryService.get_schedule(schedule_id, tenant_id)
        for key in ('name', 'scan_type', 'scan_config', 'cron_expression', 'enabled'):
            if key in data:
                setattr(schedule, key, data[key])
        if data.get('enabled') is False:
            schedule.next_run_at = None
        db.session.commit()
        return schedule

    @staticmethod
    def delete_schedule(schedule_id: UUID, tenant_id: str):
        schedule = DiscoveryService.get_schedule(schedule_id, tenant_id)
        db.session.delete(schedule)
        db.session.commit()
