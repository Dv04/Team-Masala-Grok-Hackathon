import { isDept, type Dept } from "../config.js";
import { isStatus, type DepartmentEvent, type OpsTask, type QaRequest, type QaResponse } from "../contract/types.js";
import { newId } from "../ids.js";
import { evaluateQa, qaKindForOutput, type FailCounter } from "./qa.js";

export class ContractError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

interface WebhookRegistration {
  url: string;
  dept: string;
}

export class DepartmentsEngine implements FailCounter {
  readonly events: DepartmentEvent[] = [];
  readonly tasks: OpsTask[] = [];
  readonly webhooks: WebhookRegistration[] = [];
  founderAway = false;
  repliesSentWhileAway = 0;
  private failCounts = new Map<string, number>();
  private taskKeys = new Set<string>();

  constructor(private readonly now: () => Date = () => new Date()) {}

  fails(taskId: string): number {
    return this.failCounts.get(taskId) ?? 0;
  }

  recordFail(taskId: string): void {
    this.failCounts.set(taskId, this.fails(taskId) + 1);
  }

  ingest(raw: unknown): { event: DepartmentEvent; spawned: DepartmentEvent[] } {
    const event = this.normalize(raw);
    const stored = this.store(event);
    const spawned = [stored];
    const output = stored.output ?? {};
    if (output.needs_qa === true && stored.dept !== "qa" && output.kind && "content" in output) {
      spawned.push(...this.applyNeedsQa(stored));
    }
    return { event: stored, spawned };
  }

  check(raw: unknown): { qa: QaResponse; qaEvent: DepartmentEvent } {
    if (!raw || typeof raw !== "object") throw new ContractError(400, "body must be JSON object");
    const body = raw as Record<string, unknown>;
    if (typeof body.dept !== "string" || !body.dept.trim()) throw new ContractError(400, "missing required field: dept");
    if (typeof body.task_id !== "string" || !body.task_id.trim()) throw new ContractError(400, "missing required field: task_id");
    if (typeof body.kind !== "string" || !body.kind.trim()) throw new ContractError(400, "missing required field: kind");
    if (!("content" in body)) throw new ContractError(400, "missing required field: content");
    const content = typeof body.content === "string" ? body.content : JSON.stringify(body.content);
    const requestId = typeof body.qa_request_id === "string" ? body.qa_request_id : undefined;
    const qa = evaluateQa(this, {
      dept: body.dept.trim().toLowerCase(),
      task_id: body.task_id,
      kind: body.kind.trim().toLowerCase(),
      content,
      ...(body.context !== undefined ? { context: body.context as QaRequest["context"] } : {}),
      ...(typeof body.first_contact === "boolean" ? { first_contact: body.first_contact } : {}),
      ...(body.mode === "live" || body.mode === "mock" ? { mode: body.mode } : {}),
      ...(requestId ? { qa_request_id: requestId } : {}),
    } as QaRequest & { qa_request_id?: string });
    const mode = body.mode === "live" || body.mode === "mock" ? body.mode : "mock";
    const qaEvent = this.store(this.qaEvent(body.dept.trim().toLowerCase(), body.task_id, mode, qa, body.kind, body.parent_id));
    return { qa: withExtras(qa), qaEvent };
  }

  listEvents(query: { task_id?: string; dept?: string; status?: string; limit?: string }): DepartmentEvent[] {
    const limit = Math.min(500, Math.max(1, Number(query.limit ?? 100) || 100));
    return this.events
      .filter((event) => (query.task_id ? event.task_id === query.task_id : true))
      .filter((event) => (query.dept ? event.dept === query.dept : true))
      .filter((event) => (query.status ? event.status === query.status : true))
      .slice(-limit);
  }

  kpis(): Record<string, unknown> {
    const latest = new Map<string, DepartmentEvent>();
    const started = new Map<string, number>();
    const durations: number[] = [];
    for (const event of this.events) {
      const key = `${event.dept}:${event.task_id}`;
      latest.set(key, event);
      const at = Date.parse(event.ts);
      if (!started.has(key)) started.set(key, at);
      if (event.status === "done" && event.actor !== "qa" && event.actor !== "ops" && event.actor !== "founder") {
        const begin = started.get(key);
        if (begin !== undefined && Number.isFinite(at)) durations.push(Math.max(0, at - begin));
      }
    }
    const tasksByDeptStatus: Record<string, Record<string, number>> = {
      sales: {},
      support: {},
      engineering: {},
    };
    for (const event of latest.values()) {
      const bucket = tasksByDeptStatus[event.dept] ?? {};
      bucket[event.status] = (bucket[event.status] ?? 0) + 1;
      tasksByDeptStatus[event.dept] = bucket;
    }
    const avg = durations.length ? Math.round(durations.reduce((sum, value) => sum + value, 0) / durations.length) : null;
    return {
      tasks_by_dept_status: tasksByDeptStatus,
      pending_approvals: this.pendingApprovals().length,
      pending_founder_approvals: {
        count: this.pendingApprovals().length,
        items: this.pendingApprovals().map((item) => ({
          task_id: item.task_id,
          dept: item.dept,
          summary: item.summary,
          since: item.since,
        })),
      },
      avg_time_to_done_ms: avg,
      replies_sent_while_founder_away: this.repliesSentWhileAway,
      mode: "mock",
    };
  }

  pendingApprovals(): Array<{
    task_id: string;
    dept: string;
    summary: string;
    since: string;
    mode: "live" | "mock";
    output: Record<string, unknown>;
  }> {
    const latest = new Map<string, DepartmentEvent>();
    for (const event of this.events) {
      if (event.dept === "founder") continue;
      latest.set(event.task_id, event);
    }
    const pending = [];
    for (const [taskId, event] of latest) {
      if (event.status !== "needs_approval") continue;
      const original = this.events.filter((item) => item.task_id === taskId && item.dept !== "qa");
      const source = original.at(-1) ?? event;
      const dept = original.length ? source.dept : String(event.output?.for_dept ?? event.dept);
      pending.push({
        task_id: taskId,
        dept,
        summary: source.summary,
        since: event.ts,
        mode: source.mode,
        output: source.output ?? {},
      });
    }
    return pending;
  }

  decide(taskId: string, decision: unknown, note: unknown): DepartmentEvent {
    if (decision !== "approved" && decision !== "rejected") {
      throw new ContractError(400, "decision must be approved or rejected");
    }
    const pending = this.pendingApprovals().find((item) => item.task_id === taskId);
    if (!pending) throw new ContractError(404, `task ${taskId} is not pending founder approval`);
    const noteText = typeof note === "string" ? note.slice(0, 500) : "";
    return this.store({
      ts: this.now().toISOString(),
      dept: pending.dept,
      task_id: taskId,
      actor: "founder",
      status: decision,
      summary: `Founder ${decision}: ${pending.summary}`.slice(0, 200),
      output: { decision, note: noteText, by: "founder" },
      needs_approval: false,
      mode: pending.mode,
    });
  }

  registerWebhook(url: unknown, dept: unknown): { url: string; dept: string } {
    if (typeof url !== "string" || (!url.startsWith("http://") && !url.startsWith("https://"))) {
      throw new ContractError(400, "need {url: http(s)://..., dept}");
    }
    if (typeof dept !== "string" || !dept.trim()) throw new ContractError(400, "need {url: http(s)://..., dept}");
    const name = dept.trim().toLowerCase();
    const existing = this.webhooks.find((hook) => hook.url === url && hook.dept === name);
    if (!existing) this.webhooks.push({ url, dept: name });
    return { url, dept: name };
  }

  setFounderAway(away: unknown): { away: boolean } {
    this.founderAway = away === true;
    return { away: this.founderAway };
  }

  listTasks(dept: string | undefined): OpsTask[] {
    if (dept && !isDept(dept)) throw new ContractError(400, "dept must be sales, support, or engineering");
    return this.tasks.filter((task) => (dept ? task.dept === dept : true));
  }

  enqueueInbound(input: {
    dept: Dept;
    summary: string;
    kind?: string;
    payload?: Record<string, unknown>;
    parent_id?: string;
    task_id?: string;
  }): { task: OpsTask; event: DepartmentEvent; duplicate: boolean } {
    const requestedId = input.task_id?.trim();
    const existing = requestedId
      ? this.tasks.find((item) => item.source === "inbound" && item.dept === input.dept && item.task_id === requestedId)
      : undefined;
    if (existing) {
      const event = [...this.events].reverse().find((item) => item.task_id === existing.task_id && item.dept === existing.dept);
      if (!event) throw new ContractError(500, "Inbound task is missing its event");
      return { task: existing, event, duplicate: true };
    }
    const task: OpsTask = {
      id: newId("task"),
      dept: input.dept,
      task_id: requestedId || newId("in"),
      source: "inbound",
      reason: "inbound",
      ...(input.kind ? { kind: input.kind } : {}),
      summary: input.summary,
      status: "queued",
      ...(input.payload ? { payload: input.payload } : {}),
      ...(input.parent_id ? { parent_id: input.parent_id } : {}),
      created_at: this.now().toISOString(),
    };
    this.tasks.push(task);
    const event = this.store({
      ts: task.created_at,
      dept: task.dept,
      task_id: task.task_id,
      ...(task.parent_id ? { parent_id: task.parent_id } : {}),
      actor: `${task.dept}-bot`,
      status: "queued",
      summary: task.summary,
      output: { source: "inbound", ...(task.kind ? { kind: task.kind } : {}) },
      needs_approval: false,
      mode: "mock",
    });
    return { task, event, duplicate: false as const };
  }

  markTask(id: string, status: OpsTask["status"]): void {
    const task = this.tasks.find((item) => item.id === id);
    if (task) task.status = status;
  }

  sweep(stuckAfterMs: number): { tasks: OpsTask[]; events: DepartmentEvent[] } {
    const now = this.now().getTime();
    const latest = new Map<string, DepartmentEvent>();
    for (const event of this.events) {
      if (event.actor === "ops" || event.actor === "qa" || event.actor === "founder") continue;
      latest.set(`${event.dept}:${event.task_id}`, event);
    }
    const created: OpsTask[] = [];
    const events: DepartmentEvent[] = [];
    for (const event of latest.values()) {
      const age = now - Date.parse(event.ts);
      const reason = event.status === "failed" ? "failed" : event.status === "running" && age >= stuckAfterMs ? "stuck" : null;
      if (!reason || !isDept(event.dept)) continue;
      const key = `${event.dept}:${event.task_id}:${reason}`;
      if (this.taskKeys.has(key)) continue;
      this.taskKeys.add(key);
      const task: OpsTask = {
        id: newId("ops"),
        dept: event.dept,
        task_id: event.task_id,
        source: "ops",
        reason,
        summary: `${event.dept} task ${event.task_id} is ${reason}`,
        status: "queued",
        created_at: this.now().toISOString(),
      };
      this.tasks.push(task);
      created.push(task);
      events.push(
        this.store({
          ts: task.created_at,
          dept: task.dept,
          task_id: task.task_id,
          actor: "ops",
          status: "queued",
          summary: `Ops filed a task: ${task.summary}`,
          output: { kind: "ops_task", reason: task.reason, ops_task_id: task.id },
          needs_approval: false,
          mode: "mock",
        }),
      );
    }
    return { tasks: created, events };
  }

  private applyNeedsQa(source: DepartmentEvent): DepartmentEvent[] {
    const output = source.output ?? {};
    const requestId = typeof output.qa_request_id === "string" ? output.qa_request_id : undefined;
    const kind = qaKindForOutput(output);
    const content = typeof output.content === "string" ? output.content : JSON.stringify(output.content ?? "");
    const qa = evaluateQa(this, {
      dept: source.dept,
      task_id: source.task_id,
      kind,
      content,
      ...(output.context !== undefined ? { context: output.context as QaRequest["context"] } : {}),
      ...(typeof output.first_contact === "boolean" ? { first_contact: output.first_contact } : {}),
      mode: source.mode,
      ...(requestId ? { qa_request_id: requestId } : {}),
    } as QaRequest & { qa_request_id?: string });
    const qaEvent = this.store(this.qaEvent(source.dept, source.task_id, source.mode, qa, kind, source.parent_id));
    const spawned = [qaEvent];
    const base = {
      kind: "qa_result",
      qa: { verdict: qa.verdict, score: qa.score, reasons: qa.reasons.slice(0, 4) },
      checked_kind: kind,
    };
    if (qa.verdict === "pass") {
      spawned.push(
        this.store({
          ts: this.now().toISOString(),
          dept: source.dept,
          task_id: source.task_id,
          ...(source.parent_id ? { parent_id: source.parent_id } : {}),
          actor: "auto",
          status: "done",
          summary: `${source.dept}: QA pass, cleared to send (${kind})`,
          output: base,
          needs_approval: false,
          mode: source.mode,
        }),
      );
    } else if (qa.verdict === "fail") {
      spawned.push(
        this.store({
          ts: this.now().toISOString(),
          dept: source.dept,
          task_id: source.task_id,
          ...(source.parent_id ? { parent_id: source.parent_id } : {}),
          actor: "auto",
          status: "running",
          summary: `${source.dept}: QA fail, revise and resubmit with needs_qa:true`,
          output: { ...base, next: "revise once; a 2nd fail on this task goes to the founder" },
          needs_approval: false,
          mode: source.mode,
        }),
      );
    }
    return spawned;
  }

  private qaEvent(
    dept: string,
    taskId: string,
    mode: "live" | "mock",
    qa: QaResponse,
    kind: string,
    parentId: unknown,
  ): DepartmentEvent {
    const status = qa.verdict === "pass" ? "approved" : qa.verdict === "fail" ? "rejected" : "needs_approval";
    return {
      ts: this.now().toISOString(),
      dept: "qa",
      task_id: taskId,
      ...(typeof parentId === "string" ? { parent_id: parentId } : {}),
      actor: "dev4-qa-gate",
      status,
      summary: `QA ${qa.verdict} for ${dept} ${kind} (score ${qa.score})`,
      output: {
        verdict: qa.verdict,
        score: qa.score,
        for_dept: dept,
        kind,
        qa_mode: "rules_only",
        reasons: qa.reasons.slice(0, 6),
        checks: qa.checks,
        ...(qa.qa_request_id ? { qa_request_id: qa.qa_request_id } : {}),
      },
      needs_approval: qa.verdict === "founder",
      mode,
    };
  }

  private store(event: DepartmentEvent): DepartmentEvent {
    const stored: DepartmentEvent = { ...event, output: event.output ? { ...event.output } : undefined };
    if (
      this.founderAway &&
      stored.status === "done" &&
      stored.output?.sent === true &&
      (stored.output.kind === "customer_reply" || stored.output.kind === "outbound_email")
    ) {
      this.repliesSentWhileAway += 1;
    }
    this.events.push(stored);
    return stored;
  }

  private normalize(raw: unknown): DepartmentEvent {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new ContractError(400, "event must be a JSON object");
    const body = raw as Record<string, unknown>;
    const allowed = new Set(["ts", "dept", "task_id", "status", "summary", "mode", "parent_id", "actor", "output", "needs_approval"]);
    const extra = Object.keys(body).filter((key) => !allowed.has(key));
    if (extra.length) throw new ContractError(400, `unknown fields: ${extra.sort().join(", ")} (put dept-specific data in 'output')`);
    if (typeof body.dept !== "string" || !body.dept.trim()) throw new ContractError(400, "missing required fields: dept");
    if (typeof body.task_id !== "string" || !body.task_id.trim()) throw new ContractError(400, "missing required fields: task_id");
    if (!isStatus(body.status)) throw new ContractError(400, "status must be one of queued, running, needs_approval, approved, rejected, done, failed");
    if (typeof body.summary !== "string" || !body.summary.trim()) throw new ContractError(400, "missing required fields: summary");
    if (body.mode !== "live" && body.mode !== "mock") throw new ContractError(400, "mode must be 'live' or 'mock'");
    if (body.needs_approval !== undefined && typeof body.needs_approval !== "boolean") {
      throw new ContractError(400, "needs_approval must be boolean");
    }
    if (body.output !== undefined && (!body.output || typeof body.output !== "object" || Array.isArray(body.output))) {
      throw new ContractError(400, "output must be an object");
    }
    if (SECRET_RE.test(JSON.stringify(body))) throw new ContractError(400, "event appears to contain a secret/API key; refusing to log it");
    const dept = body.dept.trim().toLowerCase();
    const output = body.output as Record<string, unknown> | undefined;
    if (output?.kind === "hire_needed" && dept !== "engineering") {
      throw new ContractError(400, "hire_needed can only be emitted by engineering");
    }
    if (output?.kind === "design_request" && dept !== "sales" && dept !== "support") {
      throw new ContractError(400, "design_request can only be emitted by sales or support");
    }
    const ts = typeof body.ts === "string" && body.ts.trim() ? body.ts : this.now().toISOString();
    if (Number.isNaN(Date.parse(ts))) throw new ContractError(400, "ts must be ISO 8601");
    return {
      ts,
      dept,
      task_id: body.task_id,
      ...(typeof body.parent_id === "string" ? { parent_id: body.parent_id } : {}),
      actor: typeof body.actor === "string" && body.actor.trim() ? body.actor : "dev2-bot",
      status: body.status,
      summary: body.summary,
      ...(output ? { output: { ...output } } : { output: {} }),
      needs_approval: body.needs_approval === true || body.status === "needs_approval",
      mode: body.mode,
    };
  }
}

const SECRET_RE = /xai-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}/;

function withExtras(qa: QaResponse): QaResponse {
  return {
    ...qa,
    mode: "rules_only",
    check_results: { rubric: "skipped (no XAI_API_KEY)", factuality: "skipped (no XAI_API_KEY)" },
  };
}
