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
import type { DepartmentEvent, OpsTask } from "./contract/types.js";
import { ContractError, DepartmentsEngine } from "./departments/engine.js";
import { planIssue } from "./engineering/bot.js";
import { HttpError, readJson, sendJson, sendText } from "./http.js";
import { newId } from "./ids.js";
import { asInboundEvent, InboundHub } from "./inbound/hub.js";
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
}

export function createApp(options: AppOptions): App {
  const engine = new DepartmentsEngine();
  const hub = new InboundHub();
  const startedTasks = new Set<string>();
  const seenListings = new Set<string>();
  const subscribers = new Set<(chunk: string) => void>();
  const stuckAfterMs = options.stuckAfterMs ?? Number(process.env.OPS_STUCK_AFTER_MS ?? 60_000);
  const mode = options.mode ?? resolveEventMode();

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

  return { server, engine, hub };

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
      const results = await consume(dept);
      sendJson(res, 200, { task: created.task, results });
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/bug") {
      sendJson(res, 200, await chainBug(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/lead") {
      sendJson(res, 200, await chainLead(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/churn") {
      sendJson(res, 200, await chainChurn(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/shipped") {
      sendJson(res, 200, await chainShipped(ctx, await chainInput(req)));
      return;
    }
    if (method === "POST" && url.pathname === "/api/chains/signals") {
      sendJson(res, 200, await chainSignals(ctx));
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
      const event = asInboundEvent(await readJson(req));
      hub.push(event);
      sendJson(res, 202, { ok: true, dept: event.dept });
      void noteListing(event);
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

  async function noteListing(event: DepartmentEvent): Promise<void> {
    if (event.output?.kind !== "listing_live" || event.dept !== "design") return;
    if (seenListings.has(event.task_id)) return;
    seenListings.add(event.task_id);
    const product = event.output.product;
    const price =
      product && typeof product === "object" && "price_usd" in product
        ? (product as { price_usd?: unknown }).price_usd
        : (event.output.price ?? null);
    const page = typeof event.output.url === "string" ? event.output.url : "";
    const shared = { kind: "listing_live", url: page, price, listing_task: event.task_id };
    await ctx.clientFor("engineering").log({
      task_id: newId("englist"),
      parent_id: event.task_id,
      status: "done",
      summary: "Engineering recorded the live listing",
      output: shared,
    });
    await ctx.clientFor("sales").log({
      task_id: newId("salelist"),
      parent_id: event.task_id,
      status: "done",
      summary: "Sales recorded the live listing",
      output: shared,
    });
    await draftReply(ctx, {
      parentId: event.task_id,
      message: {
        id: "msg_listing_buyer",
        from_name: "Buyer",
        body: "When will this listing ship?",
        channel: "email",
      },
    });
  }

  async function remoteTasks(dept?: string): Promise<OpsTask[]> {
    const url = new URL("/api/tasks", options.getDepartmentsUrl());
    if (dept) url.searchParams.set("dept", dept);
    const response = await fetch(url, { signal: AbortSignal.timeout(8000) });
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
      for (const task of tasks) {
        if (task.source !== "inbound" || !task.kind || task.status !== "queued" || startedTasks.has(task.id)) continue;
        startedTasks.add(task.id);
        if (local) engine.markTask(task.id, "running");
        try {
          const result = await dispatch(task);
          if (local) engine.markTask(task.id, "done");
          results.push({ task_id: task.task_id, kind: task.kind, result });
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
    const timeoutMs = 20000;
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
        return planIssue(ctx, { parentId });
      case "design_request":
        return draftReply(ctx, { message_id: "msg_design", parentId });
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
      const response = await fetch(new URL("/api/webhooks", departmentsUrl), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: `${selfUrl}${WEBHOOK_PATH}`, dept }),
      });
      if (!response.ok) console.warn(`Webhook registration for ${dept} returned ${response.status}`);
    } catch (error) {
      console.warn(`Webhook registration for ${dept} failed: ${error instanceof Error ? error.message : error}`);
    }
  }
}

export async function start(port = Number(process.env.WEBHOOK_PORT ?? DEFAULT_PORT)): Promise<{ url: string; close: () => Promise<void> }> {
  assertAllowedPort(port);
  const dataDir = path.join(process.cwd(), "data");
  let selfUrl = "";
  const departments = () => process.env.DEPARTMENTS_BASE_URL?.trim() || DEFAULT_DEPARTMENTS_URL;
  const dashboard = () => process.env.DASHBOARD_BASE_URL?.trim() || departments();
  const app = createApp({ dataDir, getSelfUrl: () => selfUrl, getDepartmentsUrl: departments, getDashboardUrl: dashboard });
  selfUrl = await listen(app.server, port);
  const feed = new AbortController();
  void followEventStream(departments(), app.hub, feed.signal);
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
