import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { PluginConfig } from "./types.js";

const DEFAULT_CONFIG_PATH = join(homedir(), ".recursant", "openclaw.json");

const DEFAULTS = {
  tenantId: "default",
  heartbeatIntervalMs: 30_000,
  auditBatchSize: 50,
} as const;

export function loadConfig(fromOpenClaw: Partial<PluginConfig> | undefined): PluginConfig {
  const fileConfig = readConfigFile(fromOpenClaw?.["configFile" as keyof PluginConfig] as string | undefined);
  const merged: Partial<PluginConfig> = { ...fileConfig, ...fromOpenClaw };

  const registryUrl = required(merged.registryUrl, "registryUrl");
  const enrollmentToken = required(merged.enrollmentToken, "enrollmentToken");

  return {
    registryUrl: registryUrl.replace(/\/$/, ""),
    enrollmentToken,
    tenantId: merged.tenantId ?? DEFAULTS.tenantId,
    heartbeatIntervalMs: merged.heartbeatIntervalMs ?? DEFAULTS.heartbeatIntervalMs,
    auditBatchSize: merged.auditBatchSize ?? DEFAULTS.auditBatchSize,
  };
}

function readConfigFile(explicitPath: string | undefined): Partial<PluginConfig> {
  const path = explicitPath ?? (process.env.RECURSANT_OPENCLAW_CONFIG ?? DEFAULT_CONFIG_PATH);
  try {
    const raw = readFileSync(path, "utf8");
    return JSON.parse(raw) as Partial<PluginConfig>;
  } catch (err) {
    if (explicitPath) {
      throw new Error(`Failed to read Recursant config file at ${path}: ${(err as Error).message}`);
    }
    return {};
  }
}

function required<T>(value: T | undefined, name: string): T {
  if (value === undefined || value === null || value === "") {
    throw new Error(
      `Recursant plugin config is missing "${name}". Set it via OpenClaw plugin config, ` +
        `or in ${DEFAULT_CONFIG_PATH}, or via env var RECURSANT_OPENCLAW_CONFIG=<path>.`,
    );
  }
  return value;
}
