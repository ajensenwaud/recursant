import type { InterceptorDecision, Policy } from "../types.js";

export class RateLimiter {
  private windowStart = Date.now();
  private count = 0;

  check(policy: Policy | null): InterceptorDecision {
    if (!policy?.rateLimit) return {};
    const { requestsPerMinute } = policy.rateLimit;
    const now = Date.now();
    if (now - this.windowStart >= 60_000) {
      this.windowStart = now;
      this.count = 0;
    }
    this.count += 1;
    if (this.count > requestsPerMinute) {
      return {
        block: true,
        blockReason: `Rate limit exceeded: ${requestsPerMinute} requests/minute (policy v${policy.version})`,
      };
    }
    return {};
  }

  reset(): void {
    this.windowStart = Date.now();
    this.count = 0;
  }
}
