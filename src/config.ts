export const FORBIDDEN_PORTS = [8000, 3100, 8790, 8792, 8810] as const;

export const DEFAULT_PORT = 8811;

export const WEBHOOK_PATH = "/api/webhooks/inbound";

export const DEPTS = ["sales", "support", "engineering"] as const;

export type Dept = (typeof DEPTS)[number];

export function assertAllowedPort(port: number): void {
  if (FORBIDDEN_PORTS.includes(port as (typeof FORBIDDEN_PORTS)[number])) {
    throw new Error(
      `Port ${port} is reserved by another department. Use ${DEFAULT_PORT} or any port other than ${FORBIDDEN_PORTS.join(", ")}.`,
    );
  }
}

export function isDept(value: unknown): value is Dept {
  return value === "sales" || value === "support" || value === "engineering";
}

export const DEFAULT_DEPARTMENTS_URL = "http://localhost:8810";

/** Live when this process posts to the real departments service. Tests pass mode "mock". */
export function resolveEventMode(env: NodeJS.ProcessEnv = process.env): "live" | "mock" {
  if (env.TOOLS_MODE === "mock") return "mock";
  return "live";
}

export function actorFor(dept: Dept): string {
  if (dept === "sales") return "sales-bot";
  if (dept === "support") return "support-bot";
  return "engineering-bot";
}
