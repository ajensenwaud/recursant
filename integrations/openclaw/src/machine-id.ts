import { createHash } from "node:crypto";
import { hostname, platform, arch, userInfo } from "node:os";

let cached: string | null = null;

export function getMachineId(): string {
  if (cached) return cached;
  const seed = [hostname(), platform(), arch(), userInfo().username].join("|");
  cached = createHash("sha256").update(seed).digest("hex").slice(0, 32);
  return cached;
}

export function getInstanceFingerprint(): {
  machineId: string;
  os: string;
  arch: string;
  hostname: string;
} {
  return {
    machineId: getMachineId(),
    os: platform(),
    arch: arch(),
    hostname: hostname(),
  };
}
