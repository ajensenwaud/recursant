# Egress policy core TDD evidence

This is a pure C policy predicate, not a functioning proxy or an M2 release pass. No Docker or live provider tests have run.

Initial RED: compiler could not find recursant/egress.h or core/src/compliance/egress.c. Initial GREEN: unknown classification denied public egress.

Command: `cc -std=c17 -Wall -Wextra -Werror -Icore/include tests/unit/test_egress.c core/src/compliance/egress.c -o /tmp/recursant-v4-egress-test && /tmp/recursant-v4-egress-test`

## no explicit public grant: RED

Exit: 1

```text
FAIL tests/unit/test_egress.c:18: rc_check_egress(&input) != RC_EGRESS_ALLOW
```

## no explicit public grant: GREEN

Exit: 0

```text
PASS unknown classification denies public egress
```

## unscanned final payload: RED

Exit: 1

```text
FAIL tests/unit/test_egress.c:21: rc_check_egress(&input) != RC_EGRESS_ALLOW
```

## unscanned final payload: GREEN

Exit: 0

```text
PASS unknown classification denies public egress
```

## policy generation race: RED

Exit: 1

```text
FAIL tests/unit/test_egress.c:24: rc_check_egress(&input) != RC_EGRESS_ALLOW
```

## policy generation race: GREEN

Exit: 0

```text
PASS unknown classification denies public egress
```

## null input fail closed: RED

Exit: 139

```text
/bin/bash: line 5: 2333804 Segmentation fault         (core dumped) /tmp/recursant-v4-egress-test
```

## null input fail closed: GREEN

Exit: 0

```text
PASS unknown classification denies public egress
```

## unknown enum fail closed: RED

Exit: 1

```text
FAIL tests/unit/test_egress.c:29: rc_check_egress(&input) != RC_EGRESS_ALLOW
```

## unknown enum fail closed: GREEN

Exit: 0

```text
PASS unknown classification denies public egress
```
