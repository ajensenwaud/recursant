export type InstanceStatus = "draft" | "submitted" | "active" | "blocked";

export interface PluginConfig {
  registryUrl: string;
  enrollmentToken: string;
  tenantId: string;
  heartbeatIntervalMs: number;
  auditBatchSize: number;
}

export interface EnrolledIdentity {
  agentId: string;
  instanceId: string;
  jwt: string;
  status: InstanceStatus;
}

export interface ToolCallContext {
  toolName: string;
  params: Record<string, unknown>;
  agentId: string;
  sessionId?: string;
  runId?: string;
}

export interface MessageContext {
  direction: "inbound" | "outbound";
  content: string;
  channel: string;
  sender?: string;
}

export interface LlmContext {
  provider: string;
  model: string;
  prompt: string;
  systemPrompt?: string;
}

export interface InterceptorDecision {
  block?: boolean;
  blockReason?: string;
  params?: Record<string, unknown>;
  content?: string;
  requireApproval?: {
    title: string;
    description: string;
    severity?: "info" | "warning" | "critical";
  };
}

export interface AuditEvent {
  type: "tool_call" | "llm_call" | "message" | "policy_decision";
  timestamp: string;
  agentId: string;
  instanceId: string;
  payload: Record<string, unknown>;
  decision: "allow" | "block" | "approval";
  decisionReason?: string;
}

export interface Policy {
  version: number;
  allowedTools: string[] | "*";
  blockedTools: string[];
  rateLimit: { requestsPerMinute: number } | null;
  piiRedaction: boolean;
}
