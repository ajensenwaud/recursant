import re
import struct
import zlib

MAGIC = b"KF"
VERSION = 2
MAX_VALUE = 1 << 20
_KEY = re.compile(rb"[a-z0-9._-]{1,255}")


class FrameError(ValueError):
    pass


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(data, i, end):
    shift = n = 0
    start = i
    while True:
        if i >= end:
            raise FrameError("truncated varint")
        b = data[i]
        i += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            break
        if shift > 35:
            raise FrameError("varint too long")
    if i - start > 1 and data[i - 1] == 0:
        raise FrameError("non-minimal varint")
    return n, i


def encode(pairs):
    body = bytearray([VERSION])
    body += struct.pack("<H", len(pairs)) if len(pairs) <= 0xFFFF else b""
    if len(pairs) > 0xFFFF:
        raise FrameError("too many pairs")
    for k, v in pairs:
        if not isinstance(k, str) or not isinstance(v, (bytes, bytearray)):
            raise FrameError("types")
        kb = k.encode("utf-8")
        if not _KEY.fullmatch(kb):
            raise FrameError("key")
        if len(v) > MAX_VALUE:
            raise FrameError("value too long")
        body += bytes([len(kb)]) + kb + _varint(len(v)) + bytes(v)
    return MAGIC + bytes(body) + struct.pack(">I", zlib.crc32(bytes(body)) & 0xFFFFFFFF)


def decode(data):
    data = bytes(data)
    if len(data) < 2 + 1 + 2 + 4 or data[:2] != MAGIC:
        raise FrameError("magic/short")
    end = len(data) - 4
    if struct.unpack(">I", data[end:])[0] != zlib.crc32(data[2:end]) & 0xFFFFFFFF:
        raise FrameError("crc")
    if data[2] != VERSION:
        raise FrameError("version")
    (count,) = struct.unpack("<H", data[3:5])
    i, pairs = 5, []
    for _ in range(count):
        if i >= end:
            raise FrameError("count")
        kl = data[i]
        i += 1
        if kl == 0 or i + kl > end:
            raise FrameError("key length")
        kb = data[i:i + kl]
        i += kl
        if not _KEY.fullmatch(kb):
            raise FrameError("key")
        vl, i = _read_varint(data, i, end)
        if vl > MAX_VALUE or i + vl > end:
            raise FrameError("value length")
        pairs.append((kb.decode("ascii"), data[i:i + vl]))
        i += vl
    if i != end:
        raise FrameError("trailing/count")
    return pairs
