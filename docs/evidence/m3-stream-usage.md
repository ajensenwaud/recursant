# Streamed usage capture for cost model

Commit 2f31af8 (branch m3-stream-usage). Response observer records validated usage from the stream (include_usage tail or OpenRouter accounting chunk); gateway uses it after streamed turns exactly like nonstream usage. Conflicting duplicate usage or cached>prompt fails closed.

## Verification
- RED: test_gateway_cost test_streamed_usage_tail_feeds_cache_penalty failed pre-fix (warm cache switched to physical).
- Normal CTest 26/26 x2. ASan CTest 25/26 x2: stream_tools_gateway downstream_cancel recv 3s timeout.
- Isolation check under ASan, that test only: base 496629f 5/5 pass, fix 2f31af8 5/5 pass. Classified as a load/timing flake of the full ASan suite, not a regression; tracked (previously seen on 037cf15 and m3-integration).
