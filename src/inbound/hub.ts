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

export function asInboundEvent(raw: unknown): DepartmentEvent {
  if (!raw || typeof raw !== "object") throw new Error("Webhook body must be a JSON object");
  const body = raw as Record<string, unknown>;
  const source = body.event && typeof body.event === "object" ? (body.event as Record<string, unknown>) : body;
  const forDept = source.output && typeof source.output === "object" ? (source.output as { for_dept?: unknown }).for_dept : undefined;
  const kind = source.output && typeof source.output === "object" ? (source.output as { kind?: unknown }).kind : undefined;
  const deptOk = isDept(source.dept) || (source.dept === "qa" && isDept(forDept)) || (source.dept === "design" && kind === "listing_live");
  if (!deptOk) throw new Error("Webhook dept must be sales, support, or engineering");
  if (typeof source.task_id !== "string" || typeof source.actor !== "string" || typeof source.status !== "string") {
    throw new Error("Webhook payload is missing task_id, actor, or status");
  }
  return source as unknown as DepartmentEvent;
}
