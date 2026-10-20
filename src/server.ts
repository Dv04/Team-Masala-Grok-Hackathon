import { createServer as createHttp, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { once } from "node:events";
import { pathToFileURL } from "node:url";
import { chainBug, chainChurn, chainLaunch, chainLead, chainShipped, chainSignals } from "./chains.js";
import {
  actorFor,
  assertAllowedPort,
  DEFAULT_DEPARTMENTS_URL,
  DEFAULT_PORT,
  DEPTS,
  isDept,
  resolveEventMode,
  WEBHOOK_PATH,
  type Dept,
} from "./config.js";
import { DepartmentClient, followEventStream } from "./contract/client.js";
import { AwaitingFounder } from "./contract/gate.js";
import type { DepartmentEvent, OpsTask } from "./contract/types.js";
import { ContractError, DepartmentsEngine } from "./departments/engine.js";
import { planIssue } from "./engineering/bot.js";
import { HttpError, postHub, readJson, requestJson, sendJson, sendText } from "./http.js";
import { listingFromUpstream } from "./listing.js";
import { newId } from "./ids.js";
import { classifyInbound, InboundHub } from "./inbound/hub.js";
import { handleMcp, type McpTool } from "./mcp.js";
import { panelHtml } from "./panel/page.js";
import { draftOutreach, findLeads } from "./sales/bot.js";
import { draftReply, triage } from "./support/bot.js";
import type { ServiceCtx } from "./service/types.js";

const ackedOps = new Set<string>();

export interface AppOptions {
  dataDir: string;
  getSelfUrl: () => string;
  getDepartmentsUrl: () => string;
  getDashboardUrl: () => string;
  sweepMs?: number;
  stuckAfterMs?: number;
  mode?: "live" | "mock";
}

export interface App {
  server: Server;
  engine: DepartmentsEngine;
  hub: InboundHub;
  reactStream: (event: DepartmentEvent) => Promise<void>;
}

export function createApp(options: AppOptions): App {
  const engine = new DepartmentsEngine();
  const hub = new InboundHub();
  const seenListings = new Set<string>();
  const subscribers = new Set<(chunk: string) => void>();
  const stuckAfterMs = options.stuckAfterMs ?? Number(process.env.OPS_STUCK_AFTER_MS ?? 60_000);
  const requested = options.mode ?? resolveEventMode();
  const mode = requested === "live" && !process.env.XAI_API_KEY?.trim().startsWith("xai-") ? "mock" : requested;

  const same = (left: string, right: string) => left.replace(/\/$/, "") === right.replace(/\/$/, "");

  const ctx: ServiceCtx = {
    dataDir: options.dataDir,
    mode,
    clientFor(dept: Dept) {
      const departments = options.getDepartmentsUrl();
      const dashboard = options.getDashboardUrl();
      return new DepartmentClient({
        baseUrl: departments,
        ...(same(departments, dashboard) ? {} : { dashboardUrl: dashboard }),
        dept,
        actor: actorFor(dept),
        mode,
        hub,
      });
    },
  };

  function publish(event: DepartmentEvent): void {
    const chunk = `event: event\ndata: ${JSON.stringify(event)}\n\n`;
    for (const send of subscribers) send(chunk);
  }

  function shouldFanout(event: DepartmentEvent): boolean {
    const output = event.output ?? {};
    if (event.status === "approved" || event.status === "rejected") return true;
    if (output.kind === "task" && event.status === "queued") return true;
    if (event.status === "done" && output.action && typeof output.action === "object") return true;
    return false;
  }

  async function fanout(event: DepartmentEvent): Promise<void> {
    publish(event);
    hub.push(event);
    if (!shouldFanout(event)) return;
    const targets = new Set<string>([event.dept]);
    if (event.dept === "qa" && typeof event.output?.for_dept === "string") targets.add(event.output.for_dept);
    const hooks = engine.webhooks.filter((hook) => hook.dept === "all" || targets.has(hook.dept));
    await Promise.all(
      hooks.map(async (hook) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 5000);
        try {
          await fetch(hook.url, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(event),
            signal: controller.signal,
          });
        } catch {
          // Best effort, matching dev4: no retries and no signing.
        } finally {
          clearTimeout(timer);
        }
      }),
    );
  }

  function statusFor(dept: Dept) {
    const events = engine.listEvents({ dept, limit: "500" });
    const latest = [...events].reverse().find((event) => event.actor !== "qa");
    const pending = engine.pendingApprovals().filter((item) => item.dept === dept);
    return {
      dept,
      ok: true,
      connected: true,
      mode: "mock" as const,
      service: "dev2",
      latest_status: latest?.status ?? "idle",
      latest_summary: latest?.summary ?? "Nothing yet",
      pending_approvals: pending.length,
      event_count: events.length,
      webhook_path: WEBHOOK_PATH,
    };
  }

  const botTools: McpTool[] = [
    {
      name: "sales.find_leads",
      description: "Build a fictional lead list for an ideal customer.",
      inputSchema: { type: "object", properties: { icp: { type: "string" }, limit: { type: "number" } } },
      handler: (args) => findLeads(ctx, { icp: String(args.icp ?? ""), limit: numberArg(args.limit) }),
    },
    {
      name: "sales.draft_outreach",
      description: "Draft a design request and a first-touch email that waits for the founder.",
      inputSchema: { type: "object", properties: { icp: { type: "string" }, limit: { type: "number" } } },
      handler: (args) => draftOutreach(ctx, { icp: String(args.icp ?? ""), limit: numberArg(args.limit) ?? 1 }),
    },
    {
      name: "support.triage",
      description: "Classify the sample support inbox.",
      inputSchema: { type: "object", properties: {} },
      handler: () => triage(ctx),
    },
    {
      name: "support.draft_reply",
      description: "Draft a FAQ-grounded reply. Refunds wait for the founder.",
      inputSchema: { type: "object", properties: { message_id: { type: "string" } } },
      handler: (args) => draftReply(ctx, { message_id: typeof args.message_id === "string" ? args.message_id : undefined }),
    },
    {
      name: "eng.plan_issue",
      description: "Turn a GitHub issue into a task plan and a hiring signal when needed.",
      inputSchema: { type: "object", properties: {} },
      handler: () => planIssue(ctx, {}),
    },
  ];

  const contractTools: McpTool[] = [
    {
      name: "qa.check",
      description: "Run the QA gate.",
      inputSchema: { type: "object", properties: { dept: { type: "string" }, task_id: { type: "string" }, kind: { type: "string" }, content: { type: "string" } }, required: ["dept", "task_id", "kind", "content"] },
      handler: async (args) => {
        const { qa, qaEvent } = engine.check(args);
        await fanout(qaEvent);
        return qa;
      },
    },
    {
      name: "events.append",
      description: "Append one department event.",
      inputSchema: { type: "object", properties: {} },
      handler: async (args) => {
        const result = engine.ingest(args);
        await Promise.all(result.spawned.map((event) => fanout(event)));
        return { ok: true, event: result.event };
      },
    },
    {
      name: "ops.kpis",
      description: "Read operations KPIs.",
      inputSchema: { type: "object", properties: {} },
      handler: async () => engine.kpis(),
    },
    {
      name: "approvals.pending",
      description: "List founder approvals that are still waiting.",
      inputSchema: { type: "object", properties: {} },
      handler: async () => ({ pending: engine.pendingApprovals() }),
    },
    {
      name: "approvals.decide",
      description: "Record a founder approval or rejection on the shared queue.",
      inputSchema: { type: "object", properties: { task_id: { type: "string" }, decision: { type: "string" }, note: { type: "string" } }, required: ["task_id", "decision"] },
      handler: async (args) => {
        const event = engine.decide(String(args.task_id), args.decision, args.note);
        await fanout(event);
        return event;
      },
    },
    {
      name: "automation.rules",
      description: "List the cross-department rules this mock understands.",
      inputSchema: { type: "object", properties: {} },
      handler: async () => rules(),
    },
  ];

  const server = createHttp(async (req, res) => {
    try {
      await route(req, res);
    } catch (error) {
      const status = error instanceof HttpError ? error.status : error instanceof ContractError ? error.status : 500;
      const message = error instanceof Error ? error.message : "Server error";
      if (status >= 500) console.error(message);
      sendJson(res, status, { ok: false, error: message });
    }
  });

  const timer = setInterval(() => {
    const swept = engine.sweep(stuckAfterMs);
    void Promise.all(swept.events.map((event) => fanout(event)));
  }, options.sweepMs ?? Number(process.env.OPS_SWEEP_MS ?? 60_000));
  timer.unref?.();
  server.on("close", () => clearInterval(timer));

  return { server, engine, hub, reactStream };

  async function route(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const url = new URL(req.url ?? "/", options.getSelfUrl() || "http://127.0.0.1");
    const method = req.method ?? "GET";

    if (method === "GET" && (url.pathname === "/health" || url.pathname === "/api/health")) {
      sendJson(res, 200, {
        ok: true,
        service: "dev2",
        mode,
        modes: { qa: "rules_only", sales: mode, support: mode, engineering: mode },
        webhook_path: WEBHOOK_PATH,
        panel: "/panel",
        depts: DEPTS.map((dept) => statusFor(dept)),
      });
      return;
    }
    if (method === "GET" && url.pathname === "/api/status") {
      const dept = url.searchParams.get("dept");
      if (dept) {
        if (!isDept(dept)) throw new HttpError(400, "dept must be sales, support, or engineering");
        sendJson(res, 200, statusFor(dept));
        return;
      }
      sendJson(res, 200, { ok: true, service: "dev2", mode, depts: DEPTS.map((item) => statusFor(item)) });
      return;
    }
    if (method === "GET" && url.pathname.startsWith("/api/status/")) {
      const dept = url.pathname.slice("/api/status/".length);
      if (!isDept(dept)) throw new HttpError(400, "dept must be sales, support, or engineering");
      sendJson(res, 200, statusFor(dept));
      return;
    }
    if (method === "GET" && url.pathname === "/panel") {
      sendText(res, 200, panelHtml({ mode, dashboardUrl: options.getDashboardUrl() }), "text/html; charset=utf-8", {
        "content-security-policy": "frame-ancestors *",
      });
      return;
    }
    if (method === "GET" && url.pathname === "/dashboard") {
      const company = `${options.getDashboardUrl().replace(/\/$/, "")}/dashboard`;
      sendText(
        res,
        200,
        `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Company dashboard</title></head><body><main><h1>Company dashboard</h1><p>The shared dashboard for all 13 departments is dev4's page. This process only serves the Sales, Support, and Engineering panel.</p><p><a href="/panel">Open the dev2 panel</a></p><p><a href="${company}">Configured company dashboard</a></p></main></body></html>`,
        "text/html; charset=utf-8",
      );
      return;
    }
    if (method === "GET" && url.pathname === "/api/panel/state") {
      sendJson(res, 200, {
        mode,
        dashboard_url: options.getDashboardUrl(),
        company_dashboard: `${options.getDashboardUrl().replace(/\/$/, "")}/dashboard`,
        webhook_path: WEBHOOK_PATH,
        depts: DEPTS.map((dept) => statusFor(dept)),
        events: engine.listEvents({ limit: "40" }),
        approvals: engine.pendingApprovals(),
        kpis: engine.kpis(),
      });
      return;
    }
    if (method === "POST" && url.pathname === "/api/panel/decision") {
      const body = (await readJson(req)) as { task_id?: string; decision?: string; note?: string };
      if (!body.task_id) throw new HttpError(400, "task_id is required");
      const event = await decide(body.task_id, body.decision, body.note);
      sendJson(res, 200, { ok: true, event });
      return;
    }
    if (method === "POST" && url.pathname === "/api/events") {
      const result = engine.ingest(await readJson(req));
      await Promise.all(result.spawned.map((event) => fanout(event)));
      sendJson(res, 200, { ok: true, event: result.event });
      return;
    }
    if (method === "GET" && url.pathname === "/api/events") {
      sendJson(res, 200, {
        events: engine.listEvents({
          ...(url.searchParams.get("task_id") ? { task_id: url.searchParams.get("task_id") as string } : {}),
          ...(url.searchParams.get("dept") ? { dept: url.searchParams.get("dept") as string } : {}),
          ...(url.searchParams.get("status") ? { status: url.searchParams.get("status") as string } : {}),
          ...(url.searchParams.get("limit") ? { limit: url.searchParams.get("limit") as string } : {}),
        }),
      });
      return;
    }
    if (method === "POST" && url.pathname === "/api/qa/check") {
      const result = engine.check(await readJson(req));
      await fanout(result.qaEvent);
      sendJson(res, 200, result.qa);
      return;
    }
    if (method === "GET" && url.pathname === "/api/stream") {
      res.writeHead(200, {
        "content-type": "text/event-stream",
        "cache-control": "no-store",
        connection: "keep-alive",
      });
      res.write("retry: 2000\n: connected\n\n");
      const send = (chunk: string) => {
        res.write(chunk);
      };
      subscribers.add(send);
      const ping = setInterval(() => {
        res.write(": ping\n\n");
      }, 15_000);
      ping.unref();
      req.on("close", () => {
        clearInterval(ping);
        subscribers.delete(send);
      });
      return;
    }
    if (method === "GET" && url.pathname === "/api/ops/kpis") {
      sendJson(res, 200, engine.kpis());
      return;
    }
    if (method === "GET" && url.pathname === "/api/approvals") {
      sendJson(res, 200, { pending: engine.pendingApprovals() });
      return;
    }
    if (method === "POST" && url.pathname.startsWith("/api/approvals/")) {
      const taskId = decodeURIComponent(url.pathname.slice("/api/approvals/".length));
      const body = (await readJson(req)) as { decision?: string; note?: string };
      const event = engine.decide(taskId, body.decision, body.note);
      await fanout(event);
      sendJson(res, 200, event);
      return;
    }
    if (method === "GET" && url.pathname === "/pulse") {
      let html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Pulse Studio</title></head><body><main><h1>Pulse Studio</h1><p>This mock landing page is created when Engineering launches the product.</p></main></body></html>`;
      try {
        html = await readFile(path.join(options.dataDir, "pulse", "index.html"), "utf8");
      } catch {
        // The page appears after the launch chain writes it.
      }
      sendText(res, 200, html, "text/html; charset=utf-8");
      return;
    }
    if (method === "POST" && url.pathname === "/api/webhooks") {
      const body = (await readJson(req)) as { url?: string; dept?: string };
      const hook = engine.registerWebhook(body.url, body.dept);
      sendJson(res, 200, { ok: true, ...hook, webhooks: engine.webhooks });
      return;
    }
    if (method === "POST" && url.pathname === "/api/founder/away") {
      const body = (await readJson(req)) as { away?: boolean };
      sendJson(res, 200, engine.setFounderAway(body.away));
      return;
    }
    if (method === "GET" && url.pathname === "/api/tasks") {
      const dept = url.searchParams.get("dept") ?? undefined;
      const tasks = same(options.getDepartmentsUrl(), options.getSelfUrl())
        ? engine.listTasks(dept)
        : await remoteTasks(dept);
      sendJson(res, 200, { dept: dept ?? null, tasks });
      return;
    }
    if (method === "POST" && url.pathname === "/api/tasks") {
      const body = (await readJson(req)) as InboundBody;
      const dept = body.dept ?? url.searchParams.get("dept");
      if (!isDept(dept)) throw new HttpError(400, "dept must be sales, support, or engineering");
      const created = engine.enqueueInbound({
        dept,
        summary: body.summary?.trim() || "Inbound task",
        ...(taskKind(body) ? { kind: taskKind(body) } : {}),
        ...(body.payload ? { payload: body.payload } : {}),
        ...(body.parent_id ? { parent_id: body.parent_id } : {}),
        ...(body.task_id ? { task_id: body.task_id } : {}),
      });
      if (!created.duplicate) await fanout(created.event);
      sendJson(res, 201, { task: created.task, duplicate: created.duplicate });
      return;
    }
    if (method === "POST" && url.pathname === "/api/tasks/consume") {
      const body = (await readJson(req)) as { dept?: string };
      if (body.dept && !isDept(body.dept)) throw new HttpError(400, "dept must be sales, support, or engineering");
      const results = await consume(body.dept && isDept(body.dept) ? body.dept : undefined);
      sendJson(res, 200, { results });
      return;
    }
    if (method === "POST" && url.pathname.startsWith("/api/inbound/")) {
      const dept = url.pathname.slice("/api/inbound/".length);
      if (!isDept(dept)) throw new HttpError(400, "dept must be sales, support, or engineering");
      const body = (await readJson(req)) as InboundBody;
      const created = engine.enqueueInbound({
        dept,
        summary: body.summary?.trim() || `Inbound work for ${dept}`,
        ...(taskKind(body) ? { kind: taskKind(body) } : {}),
        ...(body.payload ? { payload: body.payload } : {}),
        ...(body.parent_id ? { parent_id: body.parent_id } : {}),
        ...(body.task_id ? { task_id: body.task_id } : {}),
      });
      if (!created.duplicate) await fanout(created.event);
      if (!same(options.getDepartmentsUrl(), options.getSelfUrl())) {
        const kind = created.task.kind || deriveTaskKind(dept, created.task.summary, taskKind(body));
        try {
          const outcome = await runQueued({ ...created.task, kind });
          if (outcome.awaiting_founder) {
            sendJson(res, 202, { status: "awaiting_founder", task_id: outcome.held_task_id ?? created.task.task_id });
            return;
          }
          sendJson(res, 200, { task: created.task, results: [outcome] });
        } catch (error) {
          throw error;
        }
        return;
      }
      const results = await consume(dept);
      sendJson(res, 200, { task: created.task, results });
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/bug") {
      await sendChain(res, async () => chainBug(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/lead") {
      await sendChain(res, async () => chainLead(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/churn") {
      await sendChain(res, async () => chainChurn(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/shipped") {
      await sendChain(res, async () => chainShipped(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/signals") {
      const input = await chainInput(req);
      await sendChain(res, () => chainSignals(ctx, { timeoutMs: input.timeoutMs ?? 3000 }));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/launch") {
      sendJson(res, 200, await chainLaunch(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/ops/sweep") {
      const body = (await readJson(req)) as { stuck_after_ms?: number };
      const swept = engine.sweep(typeof body.stuck_after_ms === "number" ? body.stuck_after_ms : stuckAfterMs);
      await Promise.all(swept.events.map((event) => fanout(event)));
      sendJson(res, 200, { tasks: swept.tasks });
      return;
    }
    if (method === "POST" && url.pathname === "/api/ops/ingest") {
      const body = (await readJson(req)) as { dept?: string };
      const depts = body.dept ? [body.dept] : [...DEPTS];
      const acknowledged = [];
      for (const dept of depts) {
        if (!isDept(dept)) throw new HttpError(400, "dept must be sales, support, or engineering");
        for (const task of engine.listTasks(dept)) {
          if (ackedOps.has(task.id)) continue;
          ackedOps.add(task.id);
          const logged = await ctx.clientFor(dept).log({
            task_id: task.task_id,
            status: "done",
            summary: `Acknowledged ops task: ${task.summary}`,
            output: { kind: "ops_task", acknowledged: true, ops_task_id: task.id, reason: task.reason },
          });
          acknowledged.push(logged.event);
        }
      }
      sendJson(res, 200, { acknowledged });
      return;
    }
    if (method === "GET" && url.pathname === "/api/stream") {
      const events = engine.listEvents({ limit: url.searchParams.get("limit") ?? "50" });
      res.writeHead(200, {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache",
        connection: "close",
      });
      for (const event of events) res.write(`event: department\ndata: ${JSON.stringify(event)}\n\n`);
      res.write(`event: end\ndata: ${JSON.stringify({ done: true, mode: "mock" })}\n\n`);
      res.end();
      return;
    }
    if (method === "GET" && url.pathname === "/api/automation/rules") {
      sendJson(res, 200, rules());
      return;
    }
    if (url.pathname === WEBHOOK_PATH && method === "POST") {
      const decision = classifyInbound(await readJson(req), url.searchParams.get("dept"));
      if (decision.status === 400) throw new HttpError(400, decision.reason ?? "Bad webhook");
      if (decision.ignored || !decision.event) {
        sendJson(res, 200, { ok: true, ignored: true, reason: decision.reason ?? "ignored" });
        return;
      }
      hub.push(decision.event);
      sendJson(res, 202, { ok: true, dept: decision.target ?? decision.event.dept, react: decision.react });
      void reactInbound(decision.event, decision.react, decision.target).catch((error) => {
        console.error("inbound reaction failed", error instanceof Error ? error.message : error);
      });
      return;
    }
    if (url.pathname === WEBHOOK_PATH && method === "GET") {
      const dept = url.searchParams.get("dept");
      const events = dept && isDept(dept) ? hub.forDept(dept) : hub.events;
      sendJson(res, 200, { events });
      return;
    }
    if (method === "POST" && url.pathname === "/api/sales/find-leads") {
      const body = (await readJson(req)) as { icp?: string; limit?: number };
      sendJson(res, 200, await findLeads(ctx, body));
      return;
    }
    if (method === "POST" && url.pathname === "/api/sales/draft-outreach") {
      const body = (await readJson(req)) as { icp?: string; limit?: number };
      sendJson(res, 200, await draftOutreach(ctx, body));
      return;
    }
    if (method === "POST" && url.pathname === "/api/support/triage") {
      sendJson(res, 200, await triage(ctx));
      return;
    }
    if (method === "POST" && url.pathname === "/api/support/draft-reply") {
      const body = (await readJson(req)) as { message_id?: string };
      sendJson(res, 200, await draftReply(ctx, body));
      return;
    }
    if (method === "POST" && url.pathname === "/api/engineering/plan-issue") {
      sendJson(res, 200, await planIssue(ctx, {}));
      return;
    }
    if (url.pathname === "/mcp" || url.pathname === "/mcp/departments") {
      if (method === "GET") {
        res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
        res.write(": dev2 mcp\n\n");
        res.end();
        return;
      }
      if (method === "POST") {
        const tools = url.pathname === "/mcp" ? botTools : contractTools;
        const name = url.pathname === "/mcp" ? "dev2" : "dev2-departments-mock";
        const result = await handleMcp(await readJson(req), tools, name);
        if (result.json === null) {
          res.writeHead(result.status);
          res.end();
          return;
        }
        sendJson(res, result.status, result.json, { "mcp-protocol-version": "2025-03-26" });
        return;
      }
    }
    sendJson(res, 404, { error: "Not found" });
  }

  async function reactStream(event: DepartmentEvent): Promise<void> {
    const kind = event.output?.kind;
    if (kind === "listing_live") return noteListing(event);
    if (kind === "order_placed") return noteOrder(event);
    if (kind === "product_created" || kind === "margin_update") return noteSalesSignal(event);
  }

  async function reactInbound(
    event: DepartmentEvent,
    react: "listing" | "order" | "ack" | "store" | "task" | "sales_signal" | undefined,
    target?: Dept,
  ): Promise<void> {
    if (react === "listing") return noteListing(event);
    if (react === "order") return noteOrder(event);
    if (react === "sales_signal") return noteSalesSignal(event);
    if (react === "task" && target) {
      await runQueued(eventAsTask(event, target));
      return;
    }
    if (react === "ack" && target) return noteAck(event, target);
  }

  async function runQueued(task: OpsTask): Promise<{ task_id: string; kind: string; status: string; awaiting_founder?: boolean; held_task_id?: string; result?: unknown }> {
    const key = `queued:${task.task_id}`;
    if (seenListings.has(key)) return { task_id: task.task_id, kind: task.kind ?? "", status: "done" };
    seenListings.add(key);
    const requestId = typeof task.parent_id === "string" ? task.parent_id : undefined;
    try {
      const result = await dispatch(task);
      await postTaskStatus(task, "done", requestId, result);
      return { task_id: task.task_id, kind: task.kind ?? "", status: "done", result };
    } catch (error) {
      if (error instanceof AwaitingFounder || (error instanceof Error && /timed out/i.test(error.message))) {
        await postTaskStatus(task, "done", requestId, {
          awaiting_founder: error instanceof AwaitingFounder,
          held_task_id: error instanceof AwaitingFounder ? error.taskId : undefined,
          note: error.message,
        });
        return {
          task_id: task.task_id,
          kind: task.kind ?? "",
          status: "done",
          awaiting_founder: error instanceof AwaitingFounder,
          held_task_id: error instanceof AwaitingFounder ? error.taskId : undefined,
        };
      }
      await postTaskStatus(task, "failed", requestId, { error: error instanceof Error ? error.message : "failed" });
      throw error;
    }
  }

  async function postTaskStatus(task: OpsTask, status: "done" | "failed", requestId: string | undefined, result: unknown): Promise<void> {
    try {
      await ctx.clientFor(task.dept).log({
        task_id: task.task_id,
        ...(requestId ? { parent_id: requestId } : {}),
        status,
        summary: `${task.dept} ${status} ${task.kind ?? "task"}: ${task.summary}`.slice(0, 200),
        output: {
          kind: status === "done" ? "routed_task" : "task_failed",
          source: task.source === "orchestrator" ? "orchestrator" : "hub",
          for_dept: task.dept,
          handler: task.kind,
          ...(requestId ? { request_id: requestId } : {}),
          ...(result && typeof result === "object" ? { result } : {}),
        },
      });
    } catch (error) {
      console.error("task status post failed", error instanceof Error ? error.message : error);
    }
  }

  async function noteAck(event: DepartmentEvent, target: Dept): Promise<void> {
    const key = `ack:${target}:${event.task_id}:${event.status}:${String(event.output?.kind ?? "")}`;
    if (seenListings.has(key)) return;
    seenListings.add(key);
    await ctx.clientFor(target).log({
      task_id: newId("seen"),
      parent_id: event.task_id,
      status: "done",
      summary: `${target} received ${event.dept} ${String(event.output?.kind ?? event.status)}`,
      output: {
        kind: "dept_seen",
        source_dept: event.dept,
        source_task: event.task_id,
        trigger: event.output?.kind ?? event.status,
      },
    });
  }

  async function noteOrder(event: DepartmentEvent): Promise<void> {
    if (seenListings.has(`order:${event.task_id}`)) return;
    seenListings.add(`order:${event.task_id}`);
    await draftReply(ctx, {
      parentId: event.task_id,
      message: {
        id: "msg_pulse_order",
        from_name: "Buyer",
        body: "Where is my Pulse Studio order?",
        channel: "email",
      },
    });
  }

  async function noteListing(event: DepartmentEvent): Promise<void> {
    if (event.output?.kind !== "listing_live" || typeof event.output.listing_task === "string") return;
    if (seenListings.has(event.task_id)) return;
    seenListings.add(event.task_id);
    const listing = listingFromUpstream({ taskId: event.task_id, output: event.output, summary: event.summary });
    const page = listing.product.url;
    const shared = {
      kind: "listing_live",
      url: page,
      price: listing.product.price_usd,
      listing_task: event.task_id,
      title: listing.product.title,
      copy: listing.copy,
      copy_mode: "mock" as const,
      product: listing.product,
    };
    await ctx.clientFor("engineering").log({
      task_id: newId("englist"),
      parent_id: event.task_id,
      status: "done",
      summary: `${listing.product.title} recorded by engineering`,
      output: shared,
    });
    await ctx.clientFor("sales").log({
      task_id: newId("salelist"),
      parent_id: event.task_id,
      status: "done",
      summary: `${listing.product.title} listing is live`,
      output: shared,
    });
    await draftReply(ctx, {
      parentId: event.task_id,
      message: {
        id: "msg_listing_buyer",
        from_name: "Buyer",
        body: `When will ${listing.product.title} ship?`,
        channel: "email",
      },
    });
  }

  async function noteSalesSignal(event: DepartmentEvent): Promise<void> {
    const kind = event.output?.kind;
    if (kind !== "product_created" && kind !== "margin_update") return;
    if (event.actor === "sales-bot" || event.output?.noted === true) return;
    const key = `sales:${kind}:${event.task_id}`;
    if (seenListings.has(key)) return;
    seenListings.add(key);
    const product = event.output?.product;
    const title =
      (product && typeof product === "object" && typeof (product as { title?: unknown }).title === "string"
        ? (product as { title: string }).title
        : undefined) ||
      (typeof event.output?.title === "string" ? event.output.title : undefined) ||
      event.summary;
    await ctx.clientFor("sales").log({
      task_id: newId("sales"),
      parent_id: event.task_id,
      status: "done",
      summary: kind === "product_created" ? `Sales logged product ${title}` : `Sales logged a margin update for ${title}`,
      output: {
        kind,
        noted: true,
        title,
        ...(product !== undefined ? { product } : {}),
        ...(typeof event.output?.margin_pct === "number" ? { margin_pct: event.output.margin_pct } : {}),
      },
    });
  }

  async function remoteTasks(dept?: string): Promise<OpsTask[]> {
    const url = new URL("/api/tasks", options.getDepartmentsUrl());
    if (dept) url.searchParams.set("dept", dept);
    let response: Response;
    try {
      response = await requestJson(url, {}, { retries: 2, timeoutMs: 8000 });
    } catch (error) {
      console.error("hub task poll failed", error instanceof Error ? error.message : error);
      return [];
    }
    if (!response.ok) throw new HttpError(response.status, "Could not read the task inbox");
    const body = (await response.json()) as { tasks?: OpsTask[] };
    return body.tasks ?? [];
  }

  async function consume(dept?: Dept) {
    const depts = dept ? [dept] : [...DEPTS];
    const local = same(options.getDepartmentsUrl(), options.getSelfUrl());
    const results = [];
    for (const item of depts) {
      const tasks = local ? engine.listTasks(item) : await remoteTasks(item);
      for (const raw of tasks) {
        if (raw.source === "ops") continue;
        const task = normalizeHubTask(raw, item);
        if (!task || task.status !== "queued") continue;
        if (local) engine.markTask(task.id, "running");
        try {
          const outcome = await runQueued(task);
          if (local) engine.markTask(task.id, "done");
          results.push(outcome);
        } catch (error) {
          if (local) engine.markTask(task.id, "failed");
          throw error;
        }
      }
    }
    return results;
  }

  async function dispatch(task: OpsTask) {
    const parentId = task.task_id;
    const timeoutMs = 3000;
    switch (task.kind) {
      case "bug":
        return chainBug(ctx, { parentId, timeoutMs });
      case "lead_question":
        return chainLead(ctx, { parentId, timeoutMs });
      case "churn":
        return chainChurn(ctx, { parentId, timeoutMs });
      case "shipped":
        return chainShipped(ctx, { parentId, timeoutMs });
      case "hire_needed":
        return planIssue(ctx, { parentId, timeoutMs });
      case "design_request":
        return draftReply(ctx, { message_id: "msg_design", parentId, timeoutMs });
      default:
        throw new HttpError(400, `Unknown inbound kind ${task.kind}`);
    }
  }

  async function decide(taskId: string, decision: unknown, note: unknown): Promise<DepartmentEvent> {
    if (same(options.getDepartmentsUrl(), options.getSelfUrl())) {
      const event = engine.decide(taskId, decision, note);
      await fanout(event);
      return event;
    }
    const response = await fetch(new URL(`/api/approvals/${encodeURIComponent(taskId)}`, options.getDepartmentsUrl()), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision, note }),
    });
    if (!response.ok) throw new HttpError(response.status, await response.text());
    const body = (await response.json()) as { event?: DepartmentEvent };
    if (!body.event) throw new HttpError(502, "Approval response had no event");
    return body.event;
  }
}

const HANDLER_KINDS = new Set(["bug", "lead_question", "churn", "shipped", "hire_needed", "design_request"]);

export function deriveTaskKind(dept: Dept, title: string, detailKind?: string): string {
  if (detailKind && HANDLER_KINDS.has(detailKind)) return detailKind;
  const text = title.toLowerCase();
  if (/\b(bug|fix|broken|timeout|implement)\b/.test(text)) return "bug";
  if (/\b(lead|prospect|pipeline|sales note)\b/.test(text)) return "lead_question";
  if (/\b(churn|cancel|refund)\b/.test(text)) return "churn";
  if (/\b(shipped|launch|feature)\b/.test(text)) return "shipped";
  if (/\b(hire|hiring|candidate)\b/.test(text)) return "hire_needed";
  if (/\b(design|logo|brand)\b/.test(text)) return "design_request";
  if (dept === "sales") return "lead_question";
  if (dept === "support") return "churn";
  return "bug";
}

function eventAsTask(event: DepartmentEvent, target: Dept): OpsTask {
  const output = event.output ?? {};
  const detail = output.detail && typeof output.detail === "object" ? (output.detail as Record<string, unknown>) : {};
  const title =
    (typeof output.title === "string" && output.title) ||
    (typeof detail.text === "string" && detail.text) ||
    event.summary;
  const detailKind = typeof detail.kind === "string" ? detail.kind : undefined;
  return {
    id: event.task_id,
    dept: target,
    task_id: event.task_id,
    source: detail.source === "orchestrator" ? "orchestrator" : "inbound",
    kind: deriveTaskKind(target, title, detailKind),
    summary: title,
    status: "queued",
    ...(event.parent_id ? { parent_id: event.parent_id } : {}),
    created_at: event.ts,
    payload: detail,
  };
}

function normalizeHubTask(raw: OpsTask, fallbackDept: Dept): OpsTask | undefined {
  const extra = raw as OpsTask & { title?: string; detail?: unknown };
  const detail = extra.detail && typeof extra.detail === "object" ? (extra.detail as Record<string, unknown>) : {};
  const dept = isDept(raw.dept) ? raw.dept : fallbackDept;
  if (!raw.task_id || !isDept(dept)) return undefined;
  const title = extra.title || (typeof detail.text === "string" ? detail.text : raw.summary || "");
  const detailKind = typeof detail.kind === "string" ? detail.kind : raw.kind;
  return {
    id: raw.id || raw.task_id,
    dept,
    task_id: raw.task_id,
    source: detail.source === "orchestrator" || raw.source === "orchestrator" ? "orchestrator" : raw.source || "inbound",
    kind: deriveTaskKind(dept, `${title} ${raw.summary ?? ""}`, detailKind),
    summary: title || raw.summary || "hub task",
    status: raw.status ?? "queued",
    ...(raw.payload ? { payload: raw.payload } : Object.keys(detail).length ? { payload: detail } : {}),
    ...(raw.parent_id ? { parent_id: raw.parent_id } : {}),
    created_at: raw.created_at || new Date().toISOString(),
  };
}

async function sendChain(res: ServerResponse, run: () => Promise<unknown>): Promise<void> {
  try {
    sendJson(res, 200, await run());
  } catch (error) {
    if (error instanceof AwaitingFounder) {
      sendJson(res, 202, { status: "awaiting_founder", task_id: error.taskId });
      return;
    }
    throw error;
  }
}

interface InboundBody {
  dept?: string;
  summary?: string;
  kind?: string;
  type?: string;
  payload?: Record<string, unknown>;
  parent_id?: string;
  task_id?: string;
  timeoutMs?: number;
  icp?: string;
}

function taskKind(body: InboundBody): string | undefined {
  const payloadKind = typeof body.payload?.kind === "string" ? body.payload.kind : undefined;
  const kind = body.kind || body.type || payloadKind;
  return kind?.trim() || undefined;
}

async function chainInput(req: IncomingMessage): Promise<{ parentId?: string; timeoutMs?: number; icp?: string }> {
  const body = (await readJson(req)) as InboundBody;
  return {
    ...(body.parent_id ? { parentId: body.parent_id } : {}),
    ...(typeof body.timeoutMs === "number" ? { timeoutMs: body.timeoutMs } : {}),
    ...(body.icp ? { icp: body.icp } : {}),
  };
}

function rules() {
  return {
    mode: "mock",
    rules: [
      { when: "dept is engineering and output.kind is hire_needed", then: "HR ranks candidates and drafts outreach for founder approval" },
      { when: "dept is sales or support and output.kind is design_request", then: "Design builds a brand asset and publishes it when QA passes" },
      { when: "output.needs_qa is true", then: "QA checks the draft and posts the verdict to the department webhook" },
    ],
  };
}

function numberArg(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export async function listen(server: Server, port = 0): Promise<string> {
  if (port !== 0) assertAllowedPort(port);
  server.listen(port, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Server did not bind a TCP port");
  return `http://127.0.0.1:${address.port}`;
}

export async function registerWebhooks(departmentsUrl: string, selfUrl: string): Promise<void> {
  for (const dept of DEPTS) {
    try {
      const response = await postHub(new URL("/api/webhooks", departmentsUrl), {
        url: `${selfUrl}${WEBHOOK_PATH}?dept=${dept}`,
        dept,
      });
      if (response && !response.ok) console.warn(`Webhook registration for ${dept} returned ${response.status}`);
    } catch (error) {
      console.warn(`Webhook registration for ${dept} failed: ${error instanceof Error ? error.message : error}`);
    }
  }
}

let guardsInstalled = false;

export function installProcessGuards(): void {
  if (guardsInstalled) return;
  guardsInstalled = true;
  process.on("unhandledRejection", (reason) => {
    console.error("unhandledRejection", reason instanceof Error ? (reason.stack ?? reason.message) : reason);
  });
  process.on("uncaughtException", (error) => {
    console.error("uncaughtException", error instanceof Error ? (error.stack ?? error.message) : error);
  });
}

export async function start(port = Number(process.env.WEBHOOK_PORT ?? DEFAULT_PORT)): Promise<{ url: string; close: () => Promise<void> }> {
  installProcessGuards();
  assertAllowedPort(port);
  const dataDir = path.join(process.cwd(), "data");
  let selfUrl = "";
  const departments = () => process.env.DEPARTMENTS_BASE_URL?.trim() || DEFAULT_DEPARTMENTS_URL;
  const dashboard = () => process.env.DASHBOARD_BASE_URL?.trim() || departments();
  const app = createApp({ dataDir, getSelfUrl: () => selfUrl, getDepartmentsUrl: departments, getDashboardUrl: dashboard });
  selfUrl = await listen(app.server, port);
  const feed = new AbortController();
  void followEventStream(departments(), app.hub, feed.signal, (event) => app.reactStream(event));
  await registerWebhooks(departments(), selfUrl);
  console.log(`dev2 listening on ${selfUrl}`);
  console.log(`panel ${selfUrl}/panel`);
  console.log(`webhook ${selfUrl}${WEBHOOK_PATH}`);
  console.log(`status ${selfUrl}/api/status?dept=sales`);
  return {
    url: selfUrl,
    close: () =>
      new Promise((resolve, reject) => {
        feed.abort();
        app.server.close((error) => (error ? reject(error) : resolve()));
      }),
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  start().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}

export async function temporaryDataDir(): Promise<string> {
  return mkdtemp(path.join(tmpdir(), "dev2-"));
}
