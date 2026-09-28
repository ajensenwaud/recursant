# Bounded streamed tool routing

Synthetic loopback evidence only; no M3, native acceptance or value claim.

## Scope
Wires the independently reviewed stream_tools assembler (469658f, base a2f5a85)
through the actual response observer and gateway finish path for streamed
tool_calls responses, preserving all pins.

## Parent review (subagent reviewer lost to provider usage limit; performed by parent)
- Fragment log bounded inline (<=64KiB), no owned allocations survive feed/abort.
- Duplicate JSON keys rejected at snapshot decode; compact snapshot <=32KiB.
- Pins: unknown delta keys, unknown finish reasons, native-finish mismatch,
  invalid/missing arguments, non-contiguous indices, late tail tool_calls.
- Gateway: failed tool capture cannot fall through as plain history; tool path
  still requires pending_tools, observed_calls match, exact-result boundary.
- Reasoning content remains a pin (never stripped, never portable).

## Verification (fresh Docker builds)
- Normal: 22/22 ctest; ASan+UBSan: 22/22 ctest (detect_leaks=1).
- Gateway streamed-tool integration: 16/16 vs normal binary, 16/16 vs ASan binary.
- Every-split replay of synthetic tool wire (0..n byte splits) in unit suite.
- Note: -Werror Release build of test_interpreter.c has pre-existing unused-var
  warnings on this GCC; default (no -Werror) builds are the verified ones.
