# T02 — Strict config and validation CLI: TDD evidence

Date: 2026-09-27 (AEST). Branch: `slice/t02-strict-config`. Host: clawdy.

## RED

`tests/unit/test_config.c` written first against a not-yet-existing
`recursant/config.h`. First compile attempt:

```
$ cc -std=c17 -Wall -Wextra -Werror -Icore/include -fsyntax-only tests/unit/test_config.c
tests/unit/test_config.c:1:10: fatal error: recursant/config.h: No such file or directory
```

Saved in `docs/evidence/config-red.log`.

## Implementation

- `core/include/recursant/config.h` — `rc_config`, `rc_alias`, strict load /
  validate / check-secrets / free API, shared URL rule.
- `core/src/config/config.c` — hand-rolled strict JSON parser (value tree):
  RFC 8259 grammar, duplicate keys rejected per object, raw control
  characters rejected, strict UTF-8 validation (surrogate ranges excluded,
  overlongs rejected, > U+10FFFF rejected), `\uXXXX` with paired-surrogate
  handling, depth cap 32, integers only (fractions/exponents rejected),
  no trailing data. Schema binding with per-object key allowlists; semantic
  validation: port bounds, private http(s)/public https-only, URL authority
  rules (no userinfo, no percent-escapes, no query/fragment, numeric port),
  POSIX env-var NAME rules (no leading digit), alias uniqueness and
  endpoint-name shadowing rejected. Secret check passes NAMEs only; values
  are never stored or echoed.
- `core/src/admin/validate.c` — `recursant-validate [PATH|-]` CLI, exit
  0 valid / 1 invalid / 2 usage-IO.

## GREEN

```
$ ctest --preset dev    -> 100% tests passed (2/2: egress_policy, config_strict)
$ ctest --preset asan   -> 100% tests passed (2/2), ASan+UBSan+LSan clean
$ ./build/dev/test_config -> PASS config strictness suite (10 test groups)
```

Defects the suite caught during GREEN (all fixed, kept honestly):

1. Unknown top-level key `logging` was silently ignored by first-pass
   binding -> added `obj_keys_known` allowlists at every object level.
2. `"port": "8787"` (string) was accepted because integers are stored as
   text -> added a `num` marker to the value tree; strings are no longer
   interchangeable with numbers.
3. `api_key_env: "1BAD"` passed the name check -> POSIX names must not
   start with a digit; first-character rule added.
4. LeakSanitizer: duplicate-key path leaked the duplicate member subtree
   (member was parsed then discarded unlinked) -> link-then-check, the
   fail path frees the whole list.
5. LeakSanitizer: test helper `loads()` leaked the config when load
   succeeded but validation failed -> free on the failure path.

## CLI verification (dev build)

| Input | Result |
|---|---|
| Valid doc with `OPENROUTER_API_KEY=dummy` in env | `valid: 0 alias(es), listen 127.0.0.1:8787, secrets resolved by name`, exit 0 |
| Public endpoint on `http://` | `invalid: url scheme must be http(s) for private and https for public`, exit 1 |
| Unknown root key `logging` | `invalid: unknown key "logging" in config root`, exit 1 |
| Valid doc, secret unset | `invalid: secret not available: OPENROUTER_API_KEY`, exit 1 |
| `-h` | usage text, exit 0 |

Error strings name keys and byte offsets only; input values are never
echoed (asserted in `test_errors_do_not_echo_input`).

## Boundary

Config parsing/validation only; no socket, no endpoint contact, no secret
value is ever read into the process. The router binary does not exist yet.
