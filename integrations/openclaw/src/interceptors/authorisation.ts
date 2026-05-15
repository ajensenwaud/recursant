import type { InterceptorDecision, Policy, ToolCallContext } from "../types.js";

export function authoriseTool(ctx: ToolCallContext, policy: Policy | null): InterceptorDecision {
  if (!policy) {
    return {
      block: true,
      blockReason: "Recursant has not yet loaded a policy for this instance",
    };
  }

  if (policy.blockedTools.includes(ctx.toolName)) {
    return {
      block: true,
      blockReason: `Tool "${ctx.toolName}" is blocked by Recursant policy v${policy.version}`,
    };
  }

  if (policy.allowedTools !== "*" && !policy.allowedTools.includes(ctx.toolName)) {
    return {
      block: true,
      blockReason: `Tool "${ctx.toolName}" is not in the allowed-tools list (policy v${policy.version})`,
    };
  }

  return {};
}
