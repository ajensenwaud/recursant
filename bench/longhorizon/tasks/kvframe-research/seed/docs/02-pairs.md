# KV-frame design note 2: pair encoding

Each pair:

    key_len   1 byte           length of the UTF-8 key in bytes, 1..255
    key       key_len bytes    UTF-8
    val_len   varint           length of the value in bytes (see below)
    value     val_len bytes

varint: unsigned LEB128 (7 bits per byte, least significant group first, high bit set on all but the last byte).
Values may be empty (val_len 0). Keys may not be empty.
