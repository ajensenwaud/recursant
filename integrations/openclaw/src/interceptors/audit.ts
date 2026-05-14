import type { AuditEvent, PluginConfig } from "../types.js";
import type { RegistryClient } from "../registry-client.js";

export class AuditQueue {
  private queue: AuditEvent[] = [];
  private flushing = false;
  private timer: NodeJS.Timeout | null = null;

  constructor(
    private readonly config: PluginConfig,
    private readonly client: RegistryClient,
  ) {}

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      void this.flush();
    }, Math.max(1000, this.config.heartbeatIntervalMs / 3));
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  enqueue(event: AuditEvent): void {
    this.queue.push(event);
    console.log(`[recursant audit] enqueued ${event.type} (queue len=${this.queue.length})`);
    if (this.queue.length >= this.config.auditBatchSize) {
      void this.flush();
    }
  }

  async flush(): Promise<void> {
    if (this.flushing || this.queue.length === 0) return;
    this.flushing = true;
    const batch = this.queue.splice(0, this.config.auditBatchSize);
    console.log(`[recursant audit] flushing batch of ${batch.length}`);
    try {
      await this.client.pushAuditBatch(batch);
      console.log(`[recursant audit] flush OK`);
    } catch (err) {
      console.log(`[recursant audit] flush FAILED: ${String(err)}`);
      this.queue.unshift(...batch);
    } finally {
      this.flushing = false;
    }
  }
}
