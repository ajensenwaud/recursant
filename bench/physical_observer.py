"""Bounded metadata-only diagnostic integration, NOT a production router adapter.
Uses first-party Hermes managed-execution retention and public NeMo Relay APIs.
No SDK wrapping, harness monkeypatching, raw chunks, text, or request bodies.
"""
import threading


class PhysicalObserver:
    def __init__(self):
        from agent import relay_runtime
        self.host = relay_runtime.get_runtime()
        if self.host is None:
            raise RuntimeError('pinned Hermes Relay runtime unavailable')
        self.relay = self.host.relay
        self.events = []
        self.intercepts = []
        self.lock = threading.Lock()
        self.overflow = False
        self.name = 'recursant-physical-proof'
        self.relay.subscribers.register(self.name, self.observe)
        self.relay.intercepts.register_llm_request(self.name, 10, False, self.intercept)
        self.host.retain_managed_execution(self.name)

    def observe(self, event):
        if event.kind != 'scope':
            return
        metadata = event.metadata or {}
        row = {k: getattr(event, k) for k in ('uuid', 'parent_uuid', 'name', 'scope_category')}
        row['metadata'] = {k: metadata[k] for k in ('api_request_id', 'api_mode', 'call_role') if k in metadata}
        with self.lock:
            if len(self.events) >= 256:
                self.overflow = True
            else:
                self.events.append(row)

    def intercept(self, name, request, annotated):
        context = self.relay.capture_propagation_context()
        row = dict(parent_uuid=context.parent_uuid, root_uuid=context.root_uuid,
                   traceparent=context.to_traceparent())
        with self.lock:
            if len(self.intercepts) >= 16:
                self.overflow = True
            else:
                self.intercepts.append(row)
        # Preserve the request and annotation exactly. Relay supplies traceparent.
        return self.relay.LLMRequestInterceptOutcome(request, annotated)

    def flush(self):
        self.relay.subscribers.flush()
        if self.overflow:
            raise RuntimeError('bounded diagnostic collector overflow')

    def close(self):
        self.host.release_managed_execution(self.name)
        self.relay.intercepts.deregister_llm_request(self.name)
        self.relay.subscribers.deregister(self.name)
