Implement the "KV-frame" wire format described in the design notes under /workspace/docs/ (read ALL of them;
later notes amend earlier ones, and the errata override everything).

Create `kvframe/__init__.py` exposing:
- `encode(pairs: list[tuple[str, bytes]]) -> bytes`
- `decode(data: bytes) -> list[tuple[str, bytes]]`
- `FrameError` (raised by decode on any malformed input, and by encode on invalid input).

Add tests in `tests/`. Run `python -m unittest discover -s tests` from /workspace.
Use your file tools to create files on disk.
