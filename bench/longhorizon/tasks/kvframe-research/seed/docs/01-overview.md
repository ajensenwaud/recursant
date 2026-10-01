# KV-frame design note 1: overview

A frame carries an ordered list of key/value pairs.

Layout:

    magic   2 bytes   0x4B 0x46 ("KF")
    version 1 byte    0x01
    count   2 bytes   number of pairs, big-endian
    pairs   ...       `count` entries, see note 2
    crc     4 bytes   see note 3

Keys are text; values are raw bytes. Duplicate keys are allowed and order is preserved.
