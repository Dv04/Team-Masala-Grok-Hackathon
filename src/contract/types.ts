import type { Dept } from "../config.js";

export const STATUSES = [
  "queued",
  "running",
  "needs_approval",
  "approved",
  "rejected",
  "done",
  "failed",
] as const;

export type Status = (typeof STATUSES)[number];

export const QA_KINDS = [
  "customer_reply",
  "outbound_email",
  "refund",
  "payment",
  "public_post",
  "internal",
  "discount",
  "legal",
  "pricing",
] as const;

export type QaKind = (typeof QA_KINDS)[number];

export type QaVerdict = "pass" | "fail" | "founder";

export interface DepartmentEvent {
  ts: string;
  dept: string;
  task_id: string;
  parent_id?: string | null;
  actor: string;
  status: Status;
  summary: string;
  output?: Record<string, unknown>;
  needs_approval?: boolean;
  mode: "live" | "mock";
}

export interface QaRequest {
  dept: string;
  task_id: string;
  kind: string;
  content: string;
  context?: Record<string, unknown> | string;
  first_contact?: boolean;
  mode?: "live" | "mock";
  parent_id?: string;
}

export interface QaResponse {
  verdict: QaVerdict;
  score: number;
  reasons: string[];
  checks: string[];
  qa_request_id?: string;
  mode?: string;
  check_results?: Record<string, unknown>;
}

export interface OpsTask {
  id: string;
  dept: Dept;
  task_id: string;
  source: "ops" | "inbound" | "orchestrator";
  reason?: "stuck" | "failed" | "inbound";
  kind?: string;
  summary: string;
  status: "queued" | "running" | "done" | "failed";
  payload?: Record<string, unknown>;
  parent_id?: string | null;
  created_at: string;
}

export function isStatus(value: unknown): value is Status {
  return typeof value === "string" && (STATUSES as readonly string[]).includes(value);
}
