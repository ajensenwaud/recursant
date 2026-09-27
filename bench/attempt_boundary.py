"""Test-only FFI for the C ledger, called at real HTTP ingress, no listener.
The only source inputs are actual adapter datagrams. Not production telemetry ingestion.
"""
import ctypes as C
import threading
import time

class Headers(C.Structure):
    _fields_ = [('values', (C.c_char * 129) * 5), ('mask', C.c_uint), ('invalid', C.c_bool)]

class ID(C.Structure):
    _fields_ = [('boot', C.c_uint64 * 2), ('serial', C.c_uint64)]

class View(C.Structure):
    _fields_ = [('physical_count', C.c_uint64), ('ambiguous', C.c_bool), ('exact', C.c_bool), ('count_known', C.c_bool)]

class Boundary:
    def __init__(self):
        self.lib = C.CDLL('/probe/libattempt_probe.so')
        types = {
            'rc_attempt_probe_create': ([], C.c_void_p),
            'rc_attempt_header': ([C.POINTER(Headers), C.c_char_p, C.c_char_p], None),
            'rc_attempt_begin': ([C.c_void_p, C.c_char_p, C.POINTER(Headers), C.c_uint64, C.POINTER(ID)], C.c_int),
            'rc_attempt_finish': ([C.c_void_p, ID, C.c_bool, C.c_uint64], None),
            'rc_attempt_source_complete': ([C.c_void_p, C.c_char_p, C.POINTER(Headers), C.c_uint64], None),
            'rc_attempt_get': ([C.c_void_p, C.c_char_p, C.POINTER(Headers), ID, C.c_uint64, C.POINTER(View)], C.c_bool),
            'rc_attempt_destroy': ([C.c_void_p], None),
        }
        for name, (args, result) in types.items():
            f = getattr(self.lib, name); f.argtypes=args; f.restype=result
        self.ledger = self.lib.rc_attempt_probe_create()
        assert self.ledger
        self.rows = []
        self.lock = threading.Lock()

    def headers(self, pairs):
        h = Headers()
        for k, v in pairs:
            self.lib.rc_attempt_header(C.byref(h), k.encode('ascii'), v.encode('ascii'))
        return h

    def begin(self, wire_headers):
        with self.lock:
            h = self.headers(wire_headers.items())  # Preserve duplicate HTTP fields.
            auth = wire_headers.get('Authorization', '').encode('ascii')
            ident = ID()
            result = self.lib.rc_attempt_begin(self.ledger, auth, C.byref(h), time.monotonic_ns(), C.byref(ident))
            assert result == 2, 'auth/identity boundary must accept synthetic fixture'
            self.rows.append((h, ident))
            return ident

    def finish(self, ident, complete):
        with self.lock:
            self.lib.rc_attempt_finish(self.ledger, ident, complete, time.monotonic_ns())

    def source(self, event):
        # The fixture owns this project credential. Source authentication in a live
        # ingestion endpoint remains parent work; event fields cannot select project.
        pairs = [('X-Recursant-' + k.replace('_', '-'), event[k])
                 for k in ('task_id', 'session_id', 'turn_id', 'api_request_id', 'attempt')]
        with self.lock:
            h = self.headers(pairs)
            self.lib.rc_attempt_source_complete(self.ledger, b'Bearer synthetic-not-a-secret',
                                               C.byref(h), time.monotonic_ns())

    def views(self):
        with self.lock:
            result = []
            for h, ident in self.rows:
                v = View()
                assert self.lib.rc_attempt_get(self.ledger, b'Bearer synthetic-not-a-secret',
                    C.byref(h), ident, time.monotonic_ns(), C.byref(v))
                result.append(dict(id=f'{ident.boot[0]:016x}{ident.boot[1]:016x}:{ident.serial}',
                    physical_count=v.physical_count, ambiguous=v.ambiguous, exact=v.exact, count_known=v.count_known))
            return result

    def close(self):
        self.lib.rc_attempt_destroy(self.ledger)
