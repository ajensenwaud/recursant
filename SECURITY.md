# Security Policy

## Supported versions

Recursant is pre-1.0 and currently ships from `main`. Security fixes are
applied to `main` and the latest tagged release.

| Version | Supported |
|---|---|
| `main` (latest) | ✅ |
| Older tags | ❌ — please upgrade |

## Reporting a vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**

Instead, email the maintainer directly:

- **anders@jensenwaud.com**

Include:

- A clear description of the issue
- Steps to reproduce (or a proof-of-concept)
- Affected components (registry, sidecar, webhook, frontend, SDK)
- The Recursant commit / version you tested against
- Any suggested mitigation

You should expect:

- An acknowledgement within **5 business days**
- An initial assessment within **10 business days**
- A coordinated disclosure timeline if the report is confirmed

We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure):
the maintainer will work with you on a fix and a public advisory before
the issue is disclosed broadly.

## Scope

In scope:

- Authentication / authorization bypass in the registry API or sidecar
- Tenant isolation flaws (one tenant accessing another's data)
- mTLS / certificate handling weaknesses
- Sidecar injection bypass (an agent reaching another agent without traversing the interceptor pipeline)
- SQL injection, XSS, CSRF in the registry web UI
- Container escape from sidecar / agent containers
- Sensitive data leakage in audit records, logs, or error messages
- Guardrail bypass (malicious prompts that escape pre/post processing)

Out of scope:

- Vulnerabilities in third-party dependencies (please report upstream;
  notify us if patching is non-trivial)
- DoS attacks against single-replica local development setups
- Issues that require already-compromised cluster admin credentials

## Hall of fame

We'd like to credit responsible reporters here. If you'd prefer to remain
anonymous, just say so when you report.
