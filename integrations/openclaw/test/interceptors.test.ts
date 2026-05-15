import { describe, expect, it } from "vitest";
import { InterceptorChain } from "../src/interceptors/chain.js";
import { authoriseTool } from "../src/interceptors/authorisation.js";
import { redactPii } from "../src/interceptors/pii.js";
import { RateLimiter } from "../src/interceptors/rate-limit.js";
import type { Policy } from "../src/types.js";

const baseCtx = { agentId: "a1", params: {}, toolName: "x" };

const policy = (overrides: Partial<Policy> = {}): Policy => ({
  version: 1,
  allowedTools: "*",
  blockedTools: [],
  rateLimit: null,
  piiRedaction: false,
  ...overrides,
});

describe("authoriseTool", () => {
  it("blocks when policy is missing", () => {
    expect(authoriseTool(baseCtx, null).block).toBe(true);
  });

  it("blocks tools on the blocklist", () => {
    const d = authoriseTool({ ...baseCtx, toolName: "shell" }, policy({ blockedTools: ["shell"] }));
    expect(d.block).toBe(true);
  });

  it("blocks tools not in the allowlist", () => {
    const d = authoriseTool({ ...baseCtx, toolName: "shell" }, policy({ allowedTools: ["web_search"] }));
    expect(d.block).toBe(true);
  });

  it("allows tools on the allowlist", () => {
    const d = authoriseTool({ ...baseCtx, toolName: "web_search" }, policy({ allowedTools: ["web_search"] }));
    expect(d.block).toBeUndefined();
  });
});

describe("redactPii", () => {
  it("returns text unchanged when redaction is off", () => {
    const r = redactPii("user@example.com", policy());
    expect(r.redacted).toBe("user@example.com");
    expect(r.hits).toEqual([]);
  });

  it("redacts email when enabled", () => {
    const r = redactPii("contact user@example.com today", policy({ piiRedaction: true }));
    expect(r.redacted).not.toContain("user@example.com");
    expect(r.hits).toContain("email");
  });

  it("redacts SSN-shaped strings", () => {
    const r = redactPii("ssn 123-45-6789", policy({ piiRedaction: true }));
    expect(r.redacted).toContain("[SSN_REDACTED]");
  });
});

describe("RateLimiter", () => {
  it("allows under the limit and blocks over it", () => {
    const rl = new RateLimiter();
    const p = policy({ rateLimit: { requestsPerMinute: 2 } });
    expect(rl.check(p).block).toBeUndefined();
    expect(rl.check(p).block).toBeUndefined();
    expect(rl.check(p).block).toBe(true);
  });

  it("is a no-op when policy has no rate limit", () => {
    const rl = new RateLimiter();
    for (let i = 0; i < 100; i++) {
      expect(rl.check(policy()).block).toBeUndefined();
    }
  });
});

describe("InterceptorChain", () => {
  it("blocks tool calls when no policy is loaded", () => {
    const chain = new InterceptorChain();
    const d = chain.evaluateTool({ agentId: "a", toolName: "anything", params: {} });
    expect(d.block).toBe(true);
  });

  it("rewrites params when PII redaction is enabled", () => {
    const chain = new InterceptorChain();
    chain.setPolicy(policy({ piiRedaction: true }));
    const d = chain.evaluateTool({
      agentId: "a",
      toolName: "send_email",
      params: { to: "user@example.com", body: "hi" },
    });
    expect(d.params).toBeDefined();
    expect((d.params as Record<string, string>).to).not.toContain("user@example.com");
  });
});
