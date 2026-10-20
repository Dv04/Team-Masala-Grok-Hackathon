import { actorFor, type Dept } from "../config.js";
import { redactOutput, redactValue } from "./redact.js";
import { POLL_FALLBACK_MS, postHub, queueMirror, requestJson } from "../http.js";
import type { InboundHub } from "../inbound/hub.js";
import type { DepartmentEvent, OpsTask, QaResponse } from "./types.js";

export class DepartmentClient {
  constructor(
    private readonly options: {
      baseUrl: string;
      dashboardUrl?: string;
      dept: Dept;
      actor?: string;
      mode: "live" | "mock";
      hub?: InboundHub;
      inlineQa?: boolean;
    },
  ) {}

  get dept(): Dept {
    return this.options.dept;
  }

  async log(partial: {
    task_id: string;
    parent_id?: string | null;
    status: DepartmentEvent["status"];
    summary: string;
    output?: Record<string, unknown>;
    needs_approval?: boolean;
    mode?: "live" | "mock";
  }): Promise<{ event: DepartmentEvent; qa?: QaResponse; queued?: boolean }> {
    const copyMode = partial.output?.copy_mode;
    let mode = partial.mode ?? this.options.mode;
    if (copyMode === "mock" || (mode === "live" && !process.env.XAI_API_KEY?.trim())) mode = "mock";
    const event = {
      ts: new Date().toISOString(),
      dept: this.options.dept,
      actor: this.options.actor ?? actorFor(this.options.dept),
      mode,
      task_id: partial.task_id,
      ...(partial.parent_id ? { parent_id: partial.parent_id } : {}),
      status: partial.status,
      summary: String(redactValue(partial.summary) ?? partial.summary),
      ...(partial.output ? { output: redactOutput(partial.output) } : {}),
      needs_approval: partial.needs_approval === true || partial.status === "needs_approval",
    };
    const response = await postHub(new URL("/api/events", this.options.baseUrl), event);
    if (!response) return { event, queued: true };
    if (!response.ok) throw new Error(`Event log failed (${response.status}): ${await response.text()}`);
    const body = (await response.json()) as { ok?: boolean; event?: DepartmentEvent; qa?: QaResponse; error?: string };
    if (!body.event) throw new Error(body.error || "Event log failed: response had no event");
    await this.mirror(body.event);
    return { event: body.event, ...(body.qa ? { qa: body.qa } : {}) };
  }

  async qaVerdictCount(taskId: string): Promise<number> {
    const events = await this.listEvents({ task_id: taskId, dept: "" });
    return events.filter((event) => qaVerdict(event, taskId)).length;
  }

  private async mirror(event: DepartmentEvent): Promise<void> {
    const dashboard = this.options.dashboardUrl?.replace(/\/$/, "");
    const primary = this.options.baseUrl.replace(/\/$/, "");
    if (!dashboard || dashboard === primary) return;
    const output = { ...(event.output ?? {}) };
    delete output.needs_qa;
    delete output.content;
    queueMirror(new URL("/api/events", dashboard).href, { ...event, output, mode: this.options.mode });
  }

  async listEvents(query: { task_id?: string; status?: string; dept?: string } = {}): Promise<DepartmentEvent[]> {
    const url = new URL("/api/events", this.options.baseUrl);
    if (query.task_id) url.searchParams.set("task_id", query.task_id);
    if (query.status) url.searchParams.set("status", query.status);
    const dept = query.dept === "" ? "" : query.dept ?? this.options.dept;
    if (dept) url.searchParams.set("dept", dept);
    try {
      const response = await requestJson(url, {}, { retries: 2 });
      if (!response.ok) throw new Error(`Event read failed (${response.status})`);
      const body = (await response.json()) as { events: DepartmentEvent[] };
      return body.events;
    } catch (error) {
      console.error("hub event poll failed", error instanceof Error ? error.message : error);
      return [];
    }
  }

  async checkQa(body: Record<string, unknown>): Promise<QaResponse | null> {
    const response = await postHub(new URL("/api/qa/check", this.options.baseUrl), body);
    if (!response?.ok) return null;
    return (await response.json()) as QaResponse;
  }

  async listTasks(): Promise<OpsTask[]> {
    const url = new URL("/api/tasks", this.options.baseUrl);
    url.searchParams.set("dept", this.options.dept);
    try {
      const response = await requestJson(url, {}, { retries: 2 });
      if (!response.ok) throw new Error(`Task read failed (${response.status})`);
      const body = (await response.json()) as { tasks: OpsTask[] };
      return body.tasks;
    } catch (error) {
      console.error("hub task poll failed", error instanceof Error ? error.message : error);
      return [];
    }
  }

  async waitForQa(taskId: string, qaRequestId: string, timeoutMs = 5000, skip = 0): Promise<QaResponse> {
    const match = (event: DepartmentEvent) => qaVerdict(event, taskId, qaRequestId);
    const found = await this.waitFor(match, timeoutMs, skip);
    return this.qaFromEvent(found);
  }

  async waitForDecision(taskId: string, timeoutMs = 5000): Promise<"approved" | "rejected"> {
    const match = (event: DepartmentEvent) =>
      event.task_id === taskId &&
      event.actor === "founder" &&
      (event.status === "approved" || event.status === "rejected");
    const found = await this.waitFor(match, timeoutMs);
    return found.status === "approved" ? "approved" : "rejected";
  }

  private qaFromEvent(event: DepartmentEvent): QaResponse {
    const output = event.output ?? {};
    const verdict = output.verdict ?? output.decision;
    if (verdict !== "pass" && verdict !== "fail" && verdict !== "founder") {
      throw new Error("QA event is missing output.decision");
    }
    return {
      verdict,
      score: typeof output.score === "number" ? output.score : 0,
      reasons: Array.isArray(output.reasons) ? output.reasons.map(String) : [],
      checks: Array.isArray(output.checks) ? output.checks.map(String) : [],
      ...(typeof output.qa_request_id === "string" ? { qa_request_id: output.qa_request_id } : {}),
    };
  }

  private async waitFor(match: (event: DepartmentEvent) => boolean, timeoutMs: number, skip = 0): Promise<DepartmentEvent> {
    const started = Date.now();
    let nextPoll = 0;
    let pollGap = 300;
    for (;;) {
      const hits = this.matching(this.options.hub?.events ?? [], match);
      if (hits.length > skip) return hits[hits.length - 1] as DepartmentEvent;
      const now = Date.now();
      if (now >= nextPoll) {
        const events = await this.listEvents({ dept: "" });
        const found = this.matching(events, match);
        if (found.length > skip) return found[found.length - 1] as DepartmentEvent;
        nextPoll = now + pollGap;
        pollGap = POLL_FALLBACK_MS;
      }
      if (Date.now() - started > timeoutMs) throw new Error("Timed out waiting for a department event");
      const pause = this.options.hub ? 40 : Math.max(0, Math.min(POLL_FALLBACK_MS, nextPoll - Date.now()));
      await new Promise((resolve) => setTimeout(resolve, pause));
    }
  }

  private matching(events: DepartmentEvent[], match: (event: DepartmentEvent) => boolean): DepartmentEvent[] {
    const seen = new Set<string>();
    const hits: DepartmentEvent[] = [];
    for (const event of events) {
      if (!match(event)) continue;
      const key = `${event.ts}|${event.dept}|${event.actor}|${event.status}|${event.summary}`;
      if (seen.has(key)) continue;
      seen.add(key);
      hits.push(event);
    }
    return hits;
  }
}

function qaVerdict(event: DepartmentEvent, taskId: string, qaRequestId?: string): boolean {
  if (event.task_id !== taskId) return false;
  if (event.dept !== "qa" && event.actor !== "qa" && event.actor !== "dev4-qa-gate") return false;
  const verdict = event.output?.verdict ?? event.output?.decision;
  if (verdict !== "pass" && verdict !== "fail" && verdict !== "founder") return false;
  const request = event.output?.qa_request_id;
  return typeof request !== "string" || !qaRequestId || request === qaRequestId;
}

export async function followEventStream(baseUrl: string, hub: InboundHub, signal: AbortSignal): Promise<void> {
  while (!signal.aborted) {
    try {
      const response = await fetch(new URL("/api/stream", baseUrl), {
        headers: { accept: "text/event-stream" },
        signal,
      });
      if (!response.ok || !response.body) throw new Error(`stream ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done || signal.aborted) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const data = part
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim())
            .join("");
          if (!data) continue;
          try {
            hub.push(JSON.parse(data) as DepartmentEvent);
          } catch {
            // Comments and pings are not events.
          }
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}
