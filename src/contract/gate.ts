import { reviseContent } from "../departments/qa.js";
import { newId } from "../ids.js";
import type { DepartmentClient } from "./client.js";
import type { QaResponse } from "./types.js";

export class AwaitingFounder extends Error {
  readonly taskId: string;
  constructor(taskId: string) {
    super("awaiting_founder");
    this.name = "AwaitingFounder";
    this.taskId = taskId;
  }
}

export interface GateResult {
  sent: boolean;
  handed_off: boolean;
  verdict: QaResponse["verdict"];
  decision?: "approved" | "rejected";
  content: string;
}

export async function runCustomerGate(options: {
  client: DepartmentClient;
  taskId: string;
  parentId?: string | null;
  kind: string;
  content: string;
  context?: Record<string, unknown>;
  summary: string;
  deliver?: "send" | "handoff";
  send?: (content: string) => Promise<Record<string, unknown> | void>;
  timeoutMs?: number;
}): Promise<GateResult> {
  const deliver = options.deliver ?? "send";
  const timeoutMs = options.timeoutMs ?? 20000;
  const first = await submit(options, options.content, options.summary, timeoutMs);
  if (first.qa.verdict === "pass") return finish(options, options.content, first.qa, deliver);
  if (first.qa.verdict === "fail") {
    const revised = reviseContent(options.content, first.qa.reasons);
    await options.client.log({
      task_id: options.taskId,
      ...(options.parentId ? { parent_id: options.parentId } : {}),
      status: "running",
      summary: "Revised once using QA reasons",
      output: { kind: options.kind, revision: 1 },
    });
    const second = await submit(options, revised, "Resubmitted after one revision", timeoutMs);
    if (second.qa.verdict === "pass") return finish(options, revised, second.qa, deliver);
    return hold(options, revised, second.qa, timeoutMs, deliver);
  }
  return hold(options, options.content, first.qa, timeoutMs, deliver);
}

async function submit(
  options: {
    client: DepartmentClient;
    taskId: string;
    parentId?: string | null;
    kind: string;
    context?: Record<string, unknown>;
  },
  content: string,
  summary: string,
  timeoutMs: number,
): Promise<{ qa: QaResponse }> {
  const qaRequestId = newId("qa");
  const qaKind = options.kind === "design_request" ? "public_post" : options.kind;
  const already = await options.client.qaVerdictCount(options.taskId);
  const posted = await options.client.log({
    task_id: options.taskId,
    ...(options.parentId ? { parent_id: options.parentId } : {}),
    status: "running",
    summary,
    output: {
      needs_qa: true,
      qa_request_id: qaRequestId,
      kind: qaKind,
      deliverable: options.kind,
      content,
      context: options.context ?? {},
      ...(options.context && typeof options.context.first_contact === "boolean"
        ? { first_contact: options.context.first_contact }
        : {}),
    },
  });
  if (posted.qa?.verdict && posted.qa.qa_request_id === qaRequestId) return { qa: posted.qa };
  return { qa: await options.client.waitForQa(options.taskId, qaRequestId, timeoutMs, already) };
}

async function finish(
  options: {
    client: DepartmentClient;
    taskId: string;
    parentId?: string | null;
    kind: string;
    send?: (content: string) => Promise<Record<string, unknown> | void>;
  },
  content: string,
  qa: QaResponse,
  deliver: "send" | "handoff",
): Promise<GateResult> {
  const extra = (await options.send?.(content)) ?? {};
  const handedOff = deliver === "handoff";
  await options.client.log({
    task_id: options.taskId,
    ...(options.parentId ? { parent_id: options.parentId } : {}),
    status: "done",
    summary: handedOff ? `Handed off ${options.kind} after QA pass` : `Sent ${options.kind}`,
    output: {
      kind: options.kind,
      sent: deliver === "send",
      ...(handedOff ? { handed_off: true } : {}),
      ...(options.kind === "payment" ? { stripe_mode: "test" } : {}),
      score: qa.score,
      ...extra,
    },
  });
  return { sent: deliver === "send", handed_off: handedOff, verdict: "pass", content };
}

async function hold(
  options: {
    client: DepartmentClient;
    taskId: string;
    parentId?: string | null;
    kind: string;
    send?: (content: string) => Promise<Record<string, unknown> | void>;
  },
  content: string,
  qa: QaResponse,
  timeoutMs: number,
  deliver: "send" | "handoff",
): Promise<GateResult> {
  let decision: "approved" | "rejected";
  try {
    decision = await options.client.waitForDecision(options.taskId, timeoutMs);
  } catch (error) {
    if (error instanceof Error && /timed out/i.test(error.message)) throw new AwaitingFounder(options.taskId);
    throw error;
  }
  if (decision !== "approved") {
    await options.client.log({
      task_id: options.taskId,
      ...(options.parentId ? { parent_id: options.parentId } : {}),
      status: "done",
      summary: "Not sent: founder rejected",
      output: { kind: options.kind, sent: false, decision: "rejected" },
    });
    return { sent: false, handed_off: false, verdict: qa.verdict, decision: "rejected", content };
  }
  const sent = await finish(options, content, qa, deliver);
  return { ...sent, decision: "approved", verdict: qa.verdict };
}
