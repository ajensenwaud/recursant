import type { InterceptorDecision, Policy } from "../types.js";

const PATTERNS: Array<{ name: string; pattern: RegExp; replacement: string }> = [
  {
    name: "email",
    pattern: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
    replacement: "[EMAIL_REDACTED]",
  },
  {
    name: "ssn-us",
    pattern: /\b\d{3}-\d{2}-\d{4}\b/g,
    replacement: "[SSN_REDACTED]",
  },
  {
    name: "credit-card",
    pattern: /\b(?:\d[ -]?){13,19}\b/g,
    replacement: "[CARD_REDACTED]",
  },
  {
    name: "phone-e164",
    pattern: /\+?\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}/g,
    replacement: "[PHONE_REDACTED]",
  },
];

export function redactPii(text: string, policy: Policy | null): { redacted: string; hits: string[] } {
  if (!policy?.piiRedaction || !text) {
    return { redacted: text, hits: [] };
  }
  let redacted = text;
  const hits: string[] = [];
  for (const { name, pattern, replacement } of PATTERNS) {
    if (pattern.test(redacted)) {
      hits.push(name);
      redacted = redacted.replace(pattern, replacement);
    }
  }
  return { redacted, hits };
}

export function piiDecisionForString(
  field: "params" | "content",
  text: string,
  policy: Policy | null,
): InterceptorDecision | null {
  const { redacted, hits } = redactPii(text, policy);
  if (hits.length === 0) return null;
  if (field === "content") {
    return { content: redacted };
  }
  return {};
}
