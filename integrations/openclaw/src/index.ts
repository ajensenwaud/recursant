import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { loadConfig } from "./config.js";
import { RegistryClient } from "./registry-client.js";
import { InterceptorChain } from "./interceptors/chain.js";
import { AuditQueue } from "./interceptors/audit.js";
import { CredentialsStore, type StoredCredentials } from "./credentials-store.js";
import type {
  AuditEvent,
  EnrolledIdentity,
  LlmContext,
  MessageContext,
  ToolCallContext,
} from "./types.js";

const PLUGIN_VERSION = "0.0.1";

export default definePluginEntry({
  id: "recursant",
  name: "Recursant",
  description:
    "Governs this OpenClaw instance via the Recursant control plane — policy, PII redaction, rate limiting, and audit.",
  register(api) {
    if (api.registrationMode !== "full") {
      return;
    }
    const config = loadConfig(api.pluginConfig as Record<string, unknown> | undefined);
    const client = new RegistryClient(config, PLUGIN_VERSION);
    const chain = new InterceptorChain();
    const audit = new AuditQueue(config, client);
    const credentialsStore = new CredentialsStore();

    // Eagerly load cached credentials so hook handlers have an identity even
    // if gateway_start fires in a different register() closure (OpenClaw can
    // call register multiple times, e.g. per agent session).
    let identity: EnrolledIdentity | null = null;
    const eagerCreds = credentialsStore.load();
    if (credentialsStore.matches(eagerCreds, config.registryUrl, config.tenantId)) {
      identity = {
        agentId: eagerCreds!.agentId,
        instanceId: eagerCreds!.instanceId,
        jwt: eagerCreds!.jwt,
        status: eagerCreds!.status,
      };
      client.setIdentity(identity);
      audit.start();
    }
    let heartbeatTimer: NodeJS.Timeout | null = null;
    let policyTimer: NodeJS.Timeout | null = null;

    const fmt = (extra?: Record<string, unknown>) =>
      extra && Object.keys(extra).length > 0 ? ` ${JSON.stringify(extra)}` : "";
    const log = (msg: string, extra?: Record<string, unknown>) => {
      api.logger.info(`[recursant] ${msg}${fmt(extra)}`);
    };
    const warn = (msg: string, extra?: Record<string, unknown>) => {
      api.logger.warn(`[recursant] ${msg}${fmt(extra)}`);
    };

    const enqueueAudit = (event: Omit<AuditEvent, "agentId" | "instanceId" | "timestamp">) => {
      if (!identity) return;
      audit.enqueue({
        ...event,
        agentId: identity.agentId,
        instanceId: identity.instanceId,
        timestamp: new Date().toISOString(),
      });
    };

    api.on("gateway_start", async () => {
      try {
        if (identity) {
          log(`resumed instance ${identity.instanceId} from cached credentials`);
        } else {
          identity = await client.enroll();
          credentialsStore.save({
            ...identity,
            savedAt: new Date().toISOString(),
            registryUrl: config.registryUrl,
            tenantId: config.tenantId,
          } satisfies StoredCredentials);
          log(`enrolled new instance ${identity.instanceId} (agent ${identity.agentId}, status=${identity.status})`);
        }
        chain.setPolicy(await client.fetchPolicy());
        audit.start();
        heartbeatTimer = setInterval(() => {
          void client
            .heartbeat({ policy_version: chain.getPolicy()?.version ?? null })
            .catch((err) => warn("heartbeat failed", { err: String(err) }));
        }, config.heartbeatIntervalMs);
        policyTimer = setInterval(() => {
          void client
            .fetchPolicy()
            .then((p) => chain.setPolicy(p))
            .catch((err) => warn("policy refresh failed", { err: String(err) }));
        }, config.heartbeatIntervalMs);
      } catch (err) {
        warn(
          `enrolment failed (${String(err)}); all hooks will block until enrolment succeeds`,
        );
      }
    });

    api.on("gateway_stop", async () => {
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      if (policyTimer) clearInterval(policyTimer);
      audit.stop();
      await audit.flush();
      // Intentionally do NOT deregister on shutdown — that would consume the
      // enrollment token and require a fresh one on next start. Admin can
      // revoke via the registry UI.
    });

    api.on(
      "before_tool_call",
      async (event, hookCtx) => {
        log(`before_tool_call: ${event.toolName}`);
        const ctx: ToolCallContext = {
          toolName: event.toolName,
          params: (event.params ?? {}) as Record<string, unknown>,
          agentId: identity?.agentId ?? "unenrolled",
          sessionId: hookCtx.sessionId,
          runId: hookCtx.runId ?? event.runId,
        };
        const decision = identity
          ? chain.evaluateTool(ctx)
          : {
              block: true,
              blockReason: "Recursant has not enrolled this OpenClaw instance yet",
            };
        enqueueAudit({
          type: "tool_call",
          payload: { toolName: ctx.toolName },
          decision: decision.block ? "block" : "allow",
          decisionReason: decision.blockReason,
        });
        return decision;
      },
      { priority: 100 },
    );

    api.on("llm_input", async (event) => {
      log(`llm_input: provider=${event.provider} model=${event.model} identity=${identity ? identity.instanceId : "NULL"}`);
      const ctx: LlmContext = {
        provider: event.provider ?? "unknown",
        model: event.model ?? "unknown",
        prompt: typeof event.prompt === "string" ? event.prompt : "",
        systemPrompt: typeof event.systemPrompt === "string" ? event.systemPrompt : undefined,
      };
      const decision = chain.evaluateLlm(ctx);
      enqueueAudit({
        type: "llm_call",
        payload: { provider: ctx.provider, model: ctx.model },
        decision: decision.block ? "block" : "allow",
        decisionReason: decision.blockReason,
      });
    });

    api.on("message_received", async (event, hookCtx) => {
      const channel = hookCtx.channelId ?? "unknown";
      log(`message_received: channel=${channel}`);
      const ctx: MessageContext = {
        direction: "inbound",
        content: typeof event.content === "string" ? event.content : "",
        channel,
        sender: event.senderId ?? event.from,
      };
      const decision = chain.evaluateMessage(ctx);
      enqueueAudit({
        type: "message",
        payload: { direction: "inbound", channel: ctx.channel },
        decision: decision.block ? "block" : "allow",
      });
    });

    api.on("message_sending", async (event, hookCtx) => {
      const channel = hookCtx.channelId ?? "unknown";
      log(`message_sending: channel=${channel}`);
      const ctx: MessageContext = {
        direction: "outbound",
        content: typeof event.content === "string" ? event.content : "",
        channel,
      };
      const decision = chain.evaluateMessage(ctx);
      enqueueAudit({
        type: "message",
        payload: { direction: "outbound", channel: ctx.channel },
        decision: decision.block ? "block" : "allow",
      });
      // message_sending result accepts { content?, cancel? }; we don't rewrite
      // outbound bodies in v0, so always return undefined.
      return undefined;
    });
  },
});
