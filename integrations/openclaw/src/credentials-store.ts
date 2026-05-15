import { existsSync, mkdirSync, readFileSync, writeFileSync, chmodSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import type { EnrolledIdentity } from "./types.js";

const DEFAULT_PATH = join(homedir(), ".recursant", "openclaw-credentials.json");

export interface StoredCredentials extends EnrolledIdentity {
  savedAt: string;
  registryUrl: string;
  tenantId: string;
}

export class CredentialsStore {
  constructor(private readonly path: string = DEFAULT_PATH) {}

  load(): StoredCredentials | null {
    if (!existsSync(this.path)) return null;
    try {
      return JSON.parse(readFileSync(this.path, "utf8")) as StoredCredentials;
    } catch {
      return null;
    }
  }

  save(creds: StoredCredentials): void {
    mkdirSync(dirname(this.path), { recursive: true, mode: 0o700 });
    writeFileSync(this.path, JSON.stringify(creds, null, 2), { mode: 0o600 });
    try {
      chmodSync(this.path, 0o600);
    } catch {
      // best-effort
    }
  }

  matches(creds: StoredCredentials | null, registryUrl: string, tenantId: string): boolean {
    if (!creds) return false;
    return creds.registryUrl === registryUrl && creds.tenantId === tenantId;
  }
}
