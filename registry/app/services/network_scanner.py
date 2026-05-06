"""
Network scanner service — handles TCP connect scans, HTTP probes,
A2A agent card fetching, MCP tool enumeration, and framework fingerprinting.

Uses synchronous httpx + ThreadPoolExecutor for gevent compatibility.
The previous aiohttp/asyncio implementation caused libev assertion crashes
when running under gunicorn's gevent workers.
"""

import ipaddress
import json
import logging
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Data classes for scan results
# ============================================================================

@dataclass
class HostResult:
    """Result of probing a single host:port."""
    address: str
    port: int
    protocol: str  # http or https
    reachable: bool
    service_type: str  # a2a_agent, mcp_server, http_service, unknown
    agent_card: Optional[Dict] = None
    framework_type: Optional[str] = None
    mcp_tools: Optional[List[Dict]] = None
    tls_info: Optional[Dict] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    response_time_ms: float = 0


@dataclass
class ScanResult:
    """Aggregated result of a full scan."""
    hosts: List[HostResult]
    hosts_scanned: int = 0
    agents_found: int = 0
    tools_found: int = 0
    errors: int = 0
    duration_ms: float = 0


# ============================================================================
# Scanner configuration
# ============================================================================

@dataclass
class ScanConfig:
    """Configuration for a network scan."""
    cidrs: List[str] = field(default_factory=list)
    hosts: List[str] = field(default_factory=list)  # hostname:port or hostname
    ports: List[int] = field(default_factory=lambda: [5000, 8080, 8443, 9901])
    port_range_start: Optional[int] = None
    port_range_end: Optional[int] = None
    timeout_ms: int = 5000
    max_concurrent_probes: int = 50
    probe_delay_ms: int = 0
    auth: Optional[Dict] = None
    tls_verify: bool = True
    # Internal
    max_response_size: int = 1_048_576  # 1MB limit for responses


# ============================================================================
# Network Scanner
# ============================================================================

class NetworkScanner:
    """Synchronous network scanner for discovering A2A agents and MCP tools.

    Uses httpx + ThreadPoolExecutor for concurrency. This is compatible with
    gevent-based gunicorn workers (unlike the previous aiohttp implementation).
    """

    @staticmethod
    def scan_sync(config: ScanConfig) -> ScanResult:
        """Execute a network scan synchronously. Safe to call from any context."""
        return NetworkScanner._scan(config)

    @staticmethod
    def _scan(config: ScanConfig) -> ScanResult:
        """
        Main scan entry point. Enumerates all host:port targets from config,
        probes each one concurrently via ThreadPoolExecutor, and returns results.
        """
        start_time = time.monotonic()
        targets = NetworkScanner._enumerate_targets(config)

        timeout_s = config.timeout_ms / 1000
        verify_ssl = config.tls_verify

        hosts = []
        errors = 0

        with ThreadPoolExecutor(max_workers=config.max_concurrent_probes) as executor:
            futures = {
                executor.submit(
                    NetworkScanner._probe_host,
                    address, port, config, timeout_s, verify_ssl,
                ): (address, port)
                for address, port in targets
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if isinstance(result, HostResult):
                        hosts.append(result)
                        if result.error:
                            errors += 1
                except Exception as e:
                    errors += 1
                    addr, port = futures[future]
                    logger.warning(f"Probe failed for {addr}:{port}: {e}")

        agents_found = sum(1 for h in hosts if h.service_type == 'a2a_agent')
        tools_found = sum(
            len(h.mcp_tools) for h in hosts
            if h.mcp_tools
        )

        duration_ms = (time.monotonic() - start_time) * 1000

        return ScanResult(
            hosts=hosts,
            hosts_scanned=len(targets),
            agents_found=agents_found,
            tools_found=tools_found,
            errors=errors,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _enumerate_targets(config: ScanConfig) -> List[Tuple[str, int]]:
        """Generate list of (address, port) targets from CIDR blocks and port config."""
        targets = []

        # Determine port list
        ports = list(config.ports) if config.ports else []
        if config.port_range_start is not None and config.port_range_end is not None:
            ports.extend(range(config.port_range_start, config.port_range_end + 1))
        # Deduplicate
        ports = sorted(set(ports))

        if not ports:
            ports = [5000]

        for cidr in config.cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                for host in network.hosts():
                    for port in ports:
                        targets.append((str(host), port))
            except ValueError as e:
                logger.warning(f"Invalid CIDR {cidr}: {e}")

        # Process explicit hosts list (DNS hostnames or IPs with optional port)
        for host_entry in (config.hosts or []):
            if ':' in host_entry:
                parts = host_entry.rsplit(':', 1)
                hostname = parts[0]
                try:
                    host_port = int(parts[1])
                    targets.append((hostname, host_port))
                except ValueError:
                    # Not a valid port, treat whole string as hostname
                    for port in ports:
                        targets.append((host_entry, port))
            else:
                for port in ports:
                    targets.append((host_entry, port))

        return targets

    @staticmethod
    def _probe_host(
        address: str,
        port: int,
        config: ScanConfig,
        timeout_s: float,
        verify_ssl: bool,
    ) -> HostResult:
        """Probe a single host:port — TCP check first, then try HTTP protocols."""
        if config.probe_delay_ms > 0:
            time.sleep(config.probe_delay_ms / 1000)

        # Quick TCP check — skip all HTTP probing if port is closed
        tcp_open = NetworkScanner._tcp_connect_check(address, port, timeout_s)
        if not tcp_open:
            return HostResult(
                address=address,
                port=port,
                protocol='http',
                reachable=False,
                service_type='unknown',
                error='unreachable',
            )

        # Try HTTPS first for well-known TLS ports, otherwise HTTP first
        tls_first_ports = {443, 8443, 9443}
        if port in tls_first_ports:
            protocols = ['https', 'http']
        else:
            protocols = ['http', 'https']

        for protocol in protocols:
            result = NetworkScanner._probe_protocol(
                address, port, protocol, config, timeout_s, verify_ssl,
            )
            if result.reachable:
                return result

        # Neither protocol worked (port open but no recognized service)
        return HostResult(
            address=address,
            port=port,
            protocol='http',
            reachable=False,
            service_type='unknown',
            error='no_recognized_service',
        )

    @staticmethod
    def _tcp_connect_check(address: str, port: int, timeout_s: float) -> bool:
        """Quick TCP connect check — returns True if port is open.
        Supports both IP addresses and DNS hostnames."""
        try:
            # Use getaddrinfo to resolve DNS names and handle both IPv4/IPv6
            infos = socket.getaddrinfo(address, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for af, socktype, proto, canonname, sa in infos:
                try:
                    sock = socket.socket(af, socktype, proto)
                    sock.settimeout(min(timeout_s, 3))
                    sock.connect(sa)
                    sock.close()
                    return True
                except (socket.timeout, OSError, ConnectionRefusedError):
                    continue
            return False
        except (socket.gaierror, OSError):
            return False

    @staticmethod
    def _probe_protocol(
        address: str,
        port: int,
        protocol: str,
        config: ScanConfig,
        timeout_s: float,
        verify_ssl: bool,
    ) -> HostResult:
        """Probe a specific protocol (http or https) on a host:port."""
        base_url = f"{protocol}://{address}:{port}"
        start = time.monotonic()

        result = HostResult(
            address=address,
            port=port,
            protocol=protocol,
            reachable=False,
            service_type='unknown',
        )

        headers = {}
        if config.auth:
            auth_type = config.auth.get('type', '')
            if auth_type == 'api_key':
                headers['Authorization'] = f"Bearer {config.auth.get('key', '')}"
            elif auth_type == 'bearer':
                headers['Authorization'] = f"Bearer {config.auth.get('token', '')}"

        try:
            with httpx.Client(
                timeout=timeout_s,
                verify=verify_ssl,
                follow_redirects=False,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            ) as client:
                # 1. Try A2A well-known endpoint
                agent_card = NetworkScanner._probe_a2a(client, base_url, headers, config)
                if agent_card:
                    result.reachable = True
                    result.service_type = 'a2a_agent'
                    result.agent_card = agent_card
                    result.framework_type = NetworkScanner._detect_framework_from_card(agent_card)
                    result.metadata['agent_name'] = agent_card.get('name', '')
                    result.metadata['agent_version'] = agent_card.get('version', '')
                    result.response_time_ms = (time.monotonic() - start) * 1000
                    return result

                # 2. Try MCP SSE endpoint (real FastMCP servers)
                mcp_tools = NetworkScanner._probe_mcp_sse(client, base_url, headers, config)
                if mcp_tools is not None:
                    result.reachable = True
                    result.service_type = 'mcp_server'
                    result.mcp_tools = mcp_tools
                    result.metadata['mcp_transport'] = 'sse'
                    result.response_time_ms = (time.monotonic() - start) * 1000
                    return result

                # 3. Try MCP JSON-RPC POST endpoint (backwards compat)
                mcp_tools = NetworkScanner._probe_mcp(client, base_url, headers, config)
                if mcp_tools is not None:
                    result.reachable = True
                    result.service_type = 'mcp_server'
                    result.mcp_tools = mcp_tools
                    result.response_time_ms = (time.monotonic() - start) * 1000
                    return result

                # 4. Try framework fingerprinting
                framework = NetworkScanner._probe_framework(client, base_url, headers, config)
                if framework:
                    result.reachable = True
                    result.service_type = 'http_service'
                    result.framework_type = framework
                    result.metadata['detected_via'] = 'fingerprinting'
                    result.response_time_ms = (time.monotonic() - start) * 1000
                    return result

                # 5. Try basic HTTP connectivity
                reachable = NetworkScanner._probe_http(client, base_url, headers)
                if reachable:
                    result.reachable = True
                    result.service_type = 'http_service'
                    result.response_time_ms = (time.monotonic() - start) * 1000
                    return result

        except httpx.TimeoutException:
            result.error = 'timeout'
        except ssl.SSLError as e:
            result.error = f'ssl_error: {str(e)[:200]}'
        except httpx.ConnectError as e:
            result.error = f'connection_error: {str(e)[:200]}'
        except Exception as e:
            result.error = f'unexpected_error: {str(e)[:200]}'
            logger.warning(f"Unexpected error probing {base_url}: {e}")

        result.response_time_ms = (time.monotonic() - start) * 1000
        return result

    @staticmethod
    def _probe_a2a(
        client: httpx.Client,
        base_url: str,
        headers: Dict,
        config: ScanConfig,
    ) -> Optional[Dict]:
        """Probe /.well-known/agent.json for an A2A agent card."""
        url = f"{base_url}/.well-known/agent.json"
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            content_type = resp.headers.get('content-type', '')
            if 'json' not in content_type and 'text' not in content_type:
                return None
            # Size limit check
            body = resp.content[:config.max_response_size]
            try:
                card = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            # Basic validation: must be a dict with at least a 'name' field
            if not isinstance(card, dict):
                return None
            if 'name' not in card:
                return None
            return card
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return None

    @staticmethod
    def _probe_mcp_sse(
        client: httpx.Client,
        base_url: str,
        headers: Dict,
        config: ScanConfig,
    ) -> Optional[List[Dict]]:
        """
        Probe for real FastMCP SSE servers.
        Protocol: GET /sse → parse SSE for endpoint event → POST JSON-RPC to messages URL.
        """
        sse_url = f"{base_url}/sse"
        try:
            # Use a short timeout for the SSE connection
            sse_timeout = min(config.timeout_ms / 1000, 5)
            with httpx.Client(
                timeout=sse_timeout,
                verify=config.tls_verify,
                follow_redirects=False,
            ) as sse_client:
                with sse_client.stream(
                    'GET', sse_url,
                    headers={**headers, 'Accept': 'text/event-stream'},
                ) as response:
                    if response.status_code != 200:
                        return None
                    content_type = response.headers.get('content-type', '')
                    if 'text/event-stream' not in content_type:
                        return None

                    # Parse SSE stream for the endpoint event
                    messages_path = None
                    event_type = None
                    for line in response.iter_lines():
                        if line.startswith('event:'):
                            event_type = line[6:].strip()
                        elif line.startswith('data:'):
                            data = line[5:].strip()
                            if event_type == 'endpoint' and data:
                                messages_path = data
                                break
                        elif line == '':
                            event_type = None

                    if not messages_path:
                        return None

            # Build the full messages URL
            if messages_path.startswith('http'):
                messages_url = messages_path
            else:
                messages_url = f"{base_url}{messages_path}"

            # Send JSON-RPC initialize
            init_payload = {
                'jsonrpc': '2.0',
                'method': 'initialize',
                'params': {
                    'protocolVersion': '2024-11-05',
                    'capabilities': {},
                    'clientInfo': {'name': 'recursant-scanner', 'version': '1.0.0'},
                },
                'id': 1,
            }
            req_headers = {**headers, 'Content-Type': 'application/json'}
            resp = client.post(messages_url, json=init_payload, headers=req_headers)
            if resp.status_code != 200:
                # SSE endpoint exists but couldn't initialize — still an MCP server
                return []

            # Send tools/list
            tools_payload = {
                'jsonrpc': '2.0',
                'method': 'tools/list',
                'params': {},
                'id': 2,
            }
            resp = client.post(messages_url, json=tools_payload, headers=req_headers)
            if resp.status_code != 200:
                return []

            body = resp.content[:config.max_response_size]
            try:
                tools_result = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return []

            if isinstance(tools_result, dict) and 'result' in tools_result:
                result = tools_result['result']
                if isinstance(result, dict) and 'tools' in result:
                    tools = result['tools']
                    if isinstance(tools, list):
                        return [
                            {
                                'name': t.get('name', ''),
                                'description': t.get('description', ''),
                                'inputSchema': t.get('inputSchema', {}),
                            }
                            for t in tools
                            if isinstance(t, dict)
                        ]
            return []

        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError, Exception):
            return None

    @staticmethod
    def _probe_mcp(
        client: httpx.Client,
        base_url: str,
        headers: Dict,
        config: ScanConfig,
    ) -> Optional[List[Dict]]:
        """
        Probe for MCP server by trying JSON-RPC initialize + tools/list.
        """
        for endpoint in ['/mcp', '/sse', '/', '/rpc']:
            url = f"{base_url}{endpoint}"
            try:
                # Try JSON-RPC initialize
                init_payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "recursant-scanner", "version": "1.0.0"}
                    },
                    "id": 1
                }

                req_headers = {**headers, 'Content-Type': 'application/json'}
                resp = client.post(url, json=init_payload, headers=req_headers)
                if resp.status_code != 200:
                    continue
                body = resp.content[:config.max_response_size]
                try:
                    init_result = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                # Check if it looks like a valid MCP response
                if not isinstance(init_result, dict):
                    continue
                if 'result' not in init_result and 'jsonrpc' not in init_result:
                    continue

                # Now send tools/list
                tools_payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 2
                }
                resp = client.post(url, json=tools_payload, headers=req_headers)
                if resp.status_code != 200:
                    # Initialize worked but tools/list didn't - still an MCP server
                    return []
                body = resp.content[:config.max_response_size]
                try:
                    tools_result = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return []

                if isinstance(tools_result, dict) and 'result' in tools_result:
                    result = tools_result['result']
                    if isinstance(result, dict) and 'tools' in result:
                        tools = result['tools']
                        if isinstance(tools, list):
                            return [
                                {
                                    'name': t.get('name', ''),
                                    'description': t.get('description', ''),
                                    'inputSchema': t.get('inputSchema', {}),
                                }
                                for t in tools
                                if isinstance(t, dict)
                            ]
                return []

            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
                continue

        return None

    @staticmethod
    def _probe_framework(
        client: httpx.Client,
        base_url: str,
        headers: Dict,
        config: ScanConfig,
    ) -> Optional[str]:
        """
        Detect agent framework by probing framework-specific endpoints.
        Returns framework name or None.
        """
        # LangServe detection: /openapi.json + /invoke endpoint
        try:
            resp = client.get(f"{base_url}/openapi.json", headers=headers)
            if resp.status_code == 200:
                body = resp.content[:config.max_response_size]
                try:
                    spec = json.loads(body)
                    if isinstance(spec, dict):
                        paths = spec.get('paths', {})
                        # LangServe exposes /invoke, /batch, /stream
                        if '/invoke' in paths or any('/invoke' in p for p in paths):
                            return 'langserve'
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            pass

        # CrewAI detection: /docs + /health
        try:
            has_docs = False
            has_health = False

            resp = client.get(f"{base_url}/docs", headers=headers)
            if resp.status_code == 200:
                has_docs = True

            resp = client.get(f"{base_url}/health", headers=headers)
            if resp.status_code == 200:
                body = resp.content[:config.max_response_size]
                try:
                    health = json.loads(body)
                    if isinstance(health, dict):
                        has_health = True
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

            # CrewAI typically has both /docs (FastAPI) and /health
            if has_docs and has_health:
                # Check for /run endpoint (CrewAI specific)
                try:
                    resp = client.options(f"{base_url}/run", headers=headers)
                    if resp.status_code in (200, 204, 405):  # 405 = method not allowed but route exists
                        return 'crewai'
                except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
                    pass
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            pass

        return None

    @staticmethod
    def _probe_http(
        client: httpx.Client,
        base_url: str,
        headers: Dict,
    ) -> bool:
        """Basic HTTP reachability check."""
        for path in ['/', '/health', '/healthz']:
            try:
                resp = client.get(f"{base_url}{path}", headers=headers)
                if resp.status_code < 500:
                    return True
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
                continue
        return False

    @staticmethod
    def _detect_framework_from_card(card: Dict) -> Optional[str]:
        """Try to detect framework type from agent card metadata."""
        # Check extensions for framework hints
        extensions = card.get('extensions', {})
        if isinstance(extensions, dict):
            for key, val in extensions.items():
                if isinstance(val, dict):
                    fw = val.get('framework', val.get('agent_framework', ''))
                    if fw:
                        return fw.lower()

        # Check provider info
        provider = card.get('provider', {})
        if isinstance(provider, dict):
            org = provider.get('organization', '').lower()
            if 'langchain' in org:
                return 'langchain'
            if 'crewai' in org:
                return 'crewai'

        return None
