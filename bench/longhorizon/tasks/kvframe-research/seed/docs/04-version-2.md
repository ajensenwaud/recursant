# KV-frame design note 4: version 2 (supersedes parts of notes 1 and 3)

Version byte is now 0x02. Encoders MUST write version 2. Decoders MUST accept version 2 and MUST reject
any other version, including 1 (version 1 frames were never deployed).

Keys: must be lowercase ASCII letters, digits, '.', '-' or '_' only (still 1..255 bytes). Encoders reject
other keys; decoders reject frames containing them.

Checksum: the CRC now covers everything AFTER the magic (i.e. starting at the version byte), not the magic.
