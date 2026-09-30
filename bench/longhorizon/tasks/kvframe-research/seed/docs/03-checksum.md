# KV-frame design note 3: checksum

The trailing crc is CRC-32 (the zlib/PNG polynomial, `zlib.crc32`) of every byte of the frame before it,
starting from the magic, stored big-endian.
