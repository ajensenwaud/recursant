# KV-frame errata (authoritative; overrides all notes)

E1. The pair count is 2 bytes LITTLE-endian, not big-endian (note 1 was wrong; all deployed peers use LE).
E2. varint lengths must be minimally encoded: a decoder rejects encodings with redundant trailing 0x80/0x00 groups
    (e.g. 0x80 0x00 for zero). The maximum value length is 1,048,576 bytes; longer is rejected by both sides.
E3. A decoder must reject trailing bytes after the crc, truncated frames, and a count that does not match the
    number of pairs actually present before the crc.
