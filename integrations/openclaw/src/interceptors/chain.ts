import type {
  InterceptorDecision,
  LlmContext,
  MessageContext,
  Policy,
  ToolCallContext,
} from "../types.js";
import { authoriseTool } from "./authorisation.js";
import { redactPii } from "./pii.js";
import { RateLimiter } from "./rate-limit.js";

export class InterceptorChain {
  private policy: Policy | null = null;
  private readonly toolRate = new RateLimiter();
  private readonly llmRate = new RateLimiter();

  setPolicy(policy: Policy | null): void {
    this.policy = policy;
  }

  getPolicy(): Policy | null {
    return this.policy;
  }

  evaluateTool(ctx: ToolCallContext): InterceptorDecision {
    const rate = this.toolRate.check(this.policy);
    if (rate.block) return rate;

    const authz = authoriseTool(ctx, this.policy);
    if (authz.block) return authz;

    const piiInParams = scrubPiiInRecord(ctx.params, this.policy);
    if (piiInParams.changed) {
      return { params: piiInParams.value };
    }
    return {};
  }

  evaluateMessage(ctx: MessageContext): InterceptorDecision {
    const { redacted, hits } = redactPii(ctx.content, this.policy);
    if (hits.length > 0) {
      return { content: redacted };
    }
    return {};
  }

  evaluateLlm(ctx: LlmContext): InterceptorDecision {
    const rate = this.llmRate.check(this.policy);
    if (rate.block) return rate;

    if (this.policy?.piiRedaction) {
      const { redacted, hits } = redactPii(ctx.prompt, this.policy);
      if (hits.length > 0) {
        return { content: redacted };
      }
    }
    return {};
  }

  reset(): void {
    this.toolRate.reset();
    this.llmRate.reset();
  }
}

function scrubPiiInRecord(
  params: Record<string, unknown>,
  policy: Policy | null,
): { value: Record<string, unknown>; changed: boolean } {
  if (!policy?.piiRedaction) return { value: params, changed: false };
  let changed = false;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) {
    if (typeof v === "string") {
      const { redacted, hits } = redactPii(v, policy);
      if (hits.length > 0) {
        changed = true;
        out[k] = redacted;
        continue;
      }
    }
    out[k] = v;
  }
  return { value: out, changed };
}
