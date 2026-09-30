import struct
import unittest
import zlib
import kvframe
from kvframe import encode, decode, FrameError


def frame(body_after_magic):
    return b"KF" + body_after_magic + struct.pack(">I", zlib.crc32(body_after_magic) & 0xFFFFFFFF)


class HiddenKVFrameTests(unittest.TestCase):
    def test_exact_bytes(self):
        got = encode([("a", b"xy"), ("b.c", b"")])
        body = b"\x02" + b"\x02\x00" + b"\x01a\x02xy" + b"\x03b.c\x00"
        self.assertEqual(got, frame(body))

    def test_roundtrip_duplicates_and_long_values(self):
        pairs = [("k", b"1"), ("k", b"2"), ("z_9-x", bytes(range(256)) * 3), ("e", b"")]
        self.assertEqual(decode(encode(pairs)), pairs)
        big = [("big", b"\x00" * 300)]
        enc = encode(big)
        self.assertIn(b"\x03big\xac\x02", enc)  # LEB128 of 300
        self.assertEqual(decode(enc), big)

    def test_rejects_version_1_and_bad_crc(self):
        with self.assertRaises(FrameError):
            decode(frame(b"\x01\x00\x00"))
        good = bytearray(encode([("a", b"b")]))
        good[-1] ^= 1
        with self.assertRaises(FrameError):
            decode(bytes(good))
        # CRC computed over magic too (v1 rule) must be rejected
        body = b"\x02\x00\x00"
        wrong = b"KF" + body + struct.pack(">I", zlib.crc32(b"KF" + body) & 0xFFFFFFFF)
        with self.assertRaises(FrameError):
            decode(wrong)

    def test_key_rules(self):
        for bad in ("", "Upper", "sp ace", "ü", "x" * 256):
            with self.assertRaises(FrameError, msg=bad):
                encode([(bad, b"v")])
        with self.assertRaises(FrameError):
            decode(frame(b"\x02\x01\x00\x01A\x00"))
        self.assertEqual(decode(encode([("x" * 255, b"")]))[0][0], "x" * 255)

    def test_structural_rejections(self):
        ok = encode([("a", b"b")])
        with self.assertRaises(FrameError):
            decode(ok + b"\x00")
        with self.assertRaises(FrameError):
            decode(ok[:-5])
        with self.assertRaises(FrameError):
            decode(frame(b"\x02\x02\x00\x01a\x01b"))  # count 2, one pair
        with self.assertRaises(FrameError):
            decode(frame(b"\x02\x01\x00\x01a\x80\x00"))  # non-minimal varint zero
        with self.assertRaises(FrameError):
            decode(b"XX" + ok[2:])
        self.assertTrue(issubclass(FrameError, Exception))

    def test_value_limit(self):
        with self.assertRaises(FrameError):
            encode([("a", b"\x00" * (1048576 + 1))])
        self.assertEqual(len(decode(encode([("a", b"\x00" * 1048576)]))[0][1]), 1048576)
        n = 1048577
        v = bytearray()
        while True:
            b = n & 0x7F; n >>= 7
            v.append(b | 0x80 if n else b)
            if not n: break
        with self.assertRaises(FrameError):
            decode(frame(b"\x02\x01\x00\x01a" + bytes(v) + b"\x00" * 1048577))
