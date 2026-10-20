import { isDept, type Dept } from "../config.js";
import type { DepartmentEvent } from "../contract/types.js";

export class InboundHub {
  readonly events: DepartmentEvent[] = [];
  private readonly seen = new Set<string>();

  push(event: DepartmentEvent): void {
    const decision = typeof event.output?.decision === "string" ? event.output.decision : "";
    const request = typeof event.output?.qa_request_id === "string" ? event.output.qa_request_id : "";
    const key = `${event.dept}|${event.task_id}|${event.actor}|${event.status}|${decision}|${request}|${event.summary}`;
    if (this.seen.has(key)) return;
    this.seen.add(key);
    this.events.push(event);
  }

  forDept(dept: Dept): DepartmentEvent[] {
    return this.events.filter((event) => event.dept === dept);
  }

  find(predicate: (event: DepartmentEvent) => boolean): DepartmentEvent | undefined {
    for (let index = this.events.length - 1; index >= 0; index -= 1) {
      const event = this.events[index];
      if (event && predicate(event)) return event;
    }
    return undefined;
  }
}

const OUR_ACTORS = new Set(["sales-bot", "support-bot", "engineering-bot"]);

export interface InboundDecision {
  status: 200 | 202 | 400;
  ignored?: boolean;
  reason?: string;
  event?: DepartmentEvent;
  /** Dept that should answer. Comes from ?dept=, output.target_dept, output.for_dept, or a source dept we own. */
  target?: Dept;
  react?: "listing" | "order" | "ack" | "store" | "task" | "sales_signal";
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

/** The hub posts the emitting dept (design, ops, research, …). Route by the registration target, not that field. */
export function classifyInbound(raw: unknown, queryDept?: unknown): InboundDecision {
  const body = asRecord(raw);
  if (!body) return { status: 400, reason: "Webhook body must be a JSON object" };
  const source = asRecord(body.event) ?? body;
  const output = asRecord(source.output) ?? {};
  const kind = typeof output.kind === "string" ? output.kind : undefined;
  const query = isDept(queryDept) ? queryDept : undefined;
  const explicit = query ?? (isDept(output.target_dept) ? output.target_dept : undefined) ?? (isDept(output.for_dept) ? output.for_dept : undefined);
  const sourceDept = typeof source.dept === "string" ? source.dept : "";
  const target = explicit ?? (isDept(sourceDept) ? sourceDept : undefined);
  const hasTask = typeof source.task_id === "string" && source.task_id.length > 0;
  const hasActor = typeof source.actor === "string" && source.actor.length > 0;
  const event = source as unknown as DepartmentEvent;
  const detail = asRecord(output.detail) ?? asRecord(source.detail);
  const title = typeof output.title === "string" ? output.title : typeof source.title === "string" ? source.title : "";
  const taskLike = kind === "task" || (!kind && (title.length > 0 || !!detail || source.detail !== undefined));
  const queued = source.status === "queued" || (source.status == null && taskLike && (title.length > 0 || !!detail));

  if (!hasTask) {
    return { status: 200, ignored: true, reason: "missing task_id" };
  }
  if (!hasActor && !taskLike) {
    return { status: 200, ignored: true, reason: "missing actor" };
  }
  if (typeof source.actor === "string" && OUR_ACTORS.has(source.actor)) {
    return { status: 200, ignored: true, reason: "echo of our own event", event };
  }
  if (sourceDept === "qa" || source.actor === "founder" || source.actor === "dev4-qa-gate") {
    const qaTarget = isDept(output.for_dept) ? output.for_dept : target;
    if (!qaTarget) return { status: 200, ignored: true, reason: "qa or founder event without our dept", event };
    return { status: 202, event, target: qaTarget, react: "store" };
  }
  const routed =
    (isDept(output.for_dept) ? output.for_dept : undefined) ??
    (detail && isDept(detail.for_dept) ? detail.for_dept : undefined) ??
    target;
  if (queued && taskLike && routed) {
    return { status: 202, event, target: routed, react: "task" };
  }
  if (kind === "product_created" && source.actor !== "sales-bot" && output.noted !== true) {
    return { status: 202, event, target: "sales", react: "sales_signal" };
  }
  if (kind === "margin_update" && (routed === "sales" || sourceDept === "sales") && source.actor !== "sales-bot" && output.noted !== true) {
    return { status: 202, event, target: "sales", react: "sales_signal" };
  }
  if (kind === "listing_live" && typeof output.listing_task !== "string") {
    return { status: 202, event, target: target ?? "sales", react: "listing" };
  }
  if (kind === "order_placed") {
    return { status: 202, event, target: "support", react: "order" };
  }
  if (!target) return { status: 200, ignored: true, reason: "not for sales, support, or engineering", event };
  return { status: 202, event, target, react: "ack" };
}
