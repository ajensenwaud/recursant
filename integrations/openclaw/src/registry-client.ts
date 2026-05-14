import type { AuditEvent, EnrolledIdentity, Policy, PluginConfig } from "./types.js";
import { getInstanceFingerprint } from "./machine-id.js";

interface EnrollResponse {
  agent_id: string;
  instance_id: string;
  jwt: string;
  status: EnrolledIdentity["status"];
}

interface PolicyResponse {
  version: number;
  allowed_tools: string[] | "*";
  blocked_tools: string[];
  rate_limit: { requests_per_minute: number } | null;
  pii_redaction: boolean;
}

export class RegistryClient {
  private jwt: string | null = null;
  private identity: EnrolledIdentity | null = null;

  constructor(
    private readonly config: PluginConfig,
    private readonly pluginVersion: string,
  ) {}

  getIdentity(): EnrolledIdentity | null {
    return this.identity;
  }

  setIdentity(identity: EnrolledIdentity): void {
    this.identity = identity;
    this.jwt = identity.jwt;
  }

  async enroll(): Promise<EnrolledIdentity> {
    const fingerprint = getInstanceFingerprint();
    const response = await this.post<EnrollResponse>(
      "/v1/openclaw/instances/enroll",
      {
        enrollment_token: this.config.enrollmentToken,
        tenant_id: this.config.tenantId,
        machine_id: fingerprint.machineId,
        instance_fingerprint: fingerprint,
        plugin_version: this.pluginVersion,
      },
      { authenticated: false },
    );

    this.jwt = response.jwt;
    this.identity = {
      agentId: response.agent_id,
      instanceId: response.instance_id,
      jwt: response.jwt,
      status: response.status,
    };
    return this.identity;
  }

  async heartbeat(extras: Record<string, unknown> = {}): Promise<{ status: EnrolledIdentity["status"] }> {
    return this.post<{ status: EnrolledIdentity["status"] }>(
      "/v1/openclaw/instances/heartbeat",
      {
        plugin_version: this.pluginVersion,
        ...extras,
      },
    );
  }

  async fetchPolicy(): Promise<Policy> {
    const resp = await this.get<PolicyResponse>("/v1/openclaw/instances/policy");
    return {
      version: resp.version,
      allowedTools: resp.allowed_tools,
      blockedTools: resp.blocked_tools,
      rateLimit: resp.rate_limit
        ? { requestsPerMinute: resp.rate_limit.requests_per_minute }
        : null,
      piiRedaction: resp.pii_redaction,
    };
  }

  async pushAuditBatch(events: AuditEvent[]): Promise<void> {
    if (events.length === 0) return;
    await this.post("/v1/openclaw/instances/audit", { events });
  }

  async deregister(): Promise<void> {
    if (!this.identity) return;
    try {
      await this.post("/v1/openclaw/instances/deregister", {});
    } catch {
      // Best-effort on shutdown.
    }
  }

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.config.registryUrl}${path}`, {
      method: "GET",
      headers: this.headers(),
    });
    return this.unwrap<T>(res, path);
  }

  private async post<T>(
    path: string,
    body: Record<string, unknown>,
    opts: { authenticated?: boolean } = {},
  ): Promise<T> {
    const res = await fetch(`${this.config.registryUrl}${path}`, {
      method: "POST",
      headers: this.headers(opts.authenticated),
      body: JSON.stringify(body),
    });
    return this.unwrap<T>(res, path);
  }

  private headers(authenticated = true): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Tenant-ID": this.config.tenantId,
    };
    if (authenticated && this.jwt) {
      h["Authorization"] = `Bearer ${this.jwt}`;
    }
    return h;
  }

  private async unwrap<T>(res: Response, path: string): Promise<T> {
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Recursant ${path} failed: ${res.status} ${text}`);
    }
    return (await res.json()) as T;
  }
}
