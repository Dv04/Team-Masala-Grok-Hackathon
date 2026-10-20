import { createServer } from "node:http";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { POLL_FALLBACK_MS } from "../src/http.js";
import { createApp, listen } from "../src/server.js";

const running: Array<{ close: () => Promise<void>; dir: string }> = [];

afterEach(async () => {
  while (running.length) {
    const item = running.pop();
    if (!item) break;
    await item.close();
    await rm(item.dir, { recursive: true, force: true });
  }
});

async function boot() {
  const dir = await mkdtemp(join(tmpdir(), "dev2-"));
  let url = "";
  const app = createApp({
    dataDir: dir,
    mode: "mock",
    getSelfUrl: () => url,
    getDepartmentsUrl: () => url,
    getDashboardUrl: () => url,
  });
  url = await listen(app.server, 0);
  const close = () =>
    new Promise<void>((resolve, reject) => {
      app.server.close((error) => (error ? reject(error) : resolve()));
    });
  running.push({ close, dir });
  return url;
}

async function post(url: string, path: string, body: unknown) {
  const response = await fetch(new URL(path, url), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = (await response.json()) as Record<string, unknown>;
  return { status: response.status, json };
}

function approver(url: string, decision: "approved" | "rejected" = "approved") {
  let stop = false;
  const loop = (async () => {
    while (!stop) {
      const response = await fetch(new URL("/api/approvals?pending=true", url));
      const body = (await response.json()) as { pending?: Array<{ task_id: string }> };
      for (const item of body.pending ?? []) {
        await post(url, `/api/approvals/${item.task_id}`, { decision, note: "ok" });
      }
      await new Promise((resolve) => setTimeout(resolve, 15));
    }
  })();
  return async () => {
    stop = true;
    await loop;
  };
}

it("matches the departments event contract", async () => {
  const url = await boot();
  const ok = await post(url, "/api/events", {
    dept: "support",
    task_id: "t-1",
    actor: "dev2-bot",
    status: "running",
    summary: "Drafting a reply",
    mode: "mock",
    output: {},
  });
  expect(ok.status).toBe(200);
  expect(ok.json.ok).toBe(true);
  expect((ok.json.event as { mode: string; dept: string }).mode).toBe("mock");
  expect((ok.json.event as { dept: string }).dept).toBe("support");

  const extra = await post(url, "/api/events", {
    dept: "support",
    task_id: "t-2",
    status: "done",
    summary: "nope",
    mode: "mock",
    extra: true,
  });
  expect(extra.status).toBe(400);
  expect(extra.json.ok).toBe(false);

  const checked = await post(url, "/api/events", {
    dept: "support",
    task_id: "t-3",
    actor: "dev2-bot",
    status: "running",
    summary: "Check a shipping reply",
    mode: "mock",
    output: { needs_qa: true, kind: "customer_reply", content: "Your order shipped today and the tracking note is in the inbox." },
  });
  expect(checked.status).toBe(200);
  const events = (await fetch(new URL("/api/events?task_id=t-3", url)).then((response) => response.json())) as {
    events: Array<{ dept: string; status: string; output?: { verdict?: string; for_dept?: string } }>;
  };
  const qa = events.events.find((event) => event.dept === "qa");
  expect(qa?.status).toBe("approved");
  expect(qa?.output?.verdict).toBe("pass");
  expect(qa?.output?.for_dept).toBe("support");
});

it("sends a founder approval to the sales webhook", async () => {
  const url = await boot();
  const seen: Array<{ actor?: string; status?: string; dept?: string }> = [];
  const hook = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      seen.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      res.end("{}");
    });
  });
  hook.listen(0, "127.0.0.1");
  await once(hook, "listening");
  const address = hook.address();
  if (!address || typeof address === "string") throw new Error("hook did not bind");
  const hookUrl = `http://127.0.0.1:${address.port}/hook`;

  try {
    expect((await post(url, "/api/webhooks", { url: hookUrl, dept: "sales" })).json.ok).toBe(true);
    const draft = post(url, "/api/sales/draft-outreach", { limit: 1, skip_design: true });
    const stop = approver(url);
    const result = await draft;
    await stop();
    expect(result.status).toBe(200);
    expect(seen.some((event) => event.actor === "founder" && event.status === "approved" && event.dept === "sales")).toBe(true);
  } finally {
    if (hook.listening) {
      await new Promise<void>((resolve, reject) => hook.close((error) => (error ? reject(error) : resolve())));
    }
  }
});

it("passes a grounded support reply and holds a refund until approval", async () => {
  const url = await boot();
  const shipped = await post(url, "/api/support/draft-reply", { message_id: "msg_ship" });
  expect(shipped.status).toBe(200);
  expect((shipped.json as { sent?: boolean }).sent).toBe(true);

  const pendingRefund = post(url, "/api/support/draft-reply", { message_id: "msg_refund" });
  const approvals = await fetch(new URL("/api/approvals?pending=true", url));
  let taskId = "";
  const started = Date.now();
  while (!taskId && Date.now() - started < 4000) {
    const body = (await (await fetch(new URL("/api/approvals?pending=true", url))).json()) as {
      pending: Array<{ task_id: string }>;
    };
    taskId = body.pending[0]?.task_id ?? "";
    if (!taskId) await new Promise((resolve) => setTimeout(resolve, 20));
  }
  expect(taskId).not.toBe("");
  await post(url, `/api/approvals/${taskId}`, { decision: "rejected", note: "no" });
  const rejected = await pendingRefund;
  expect((rejected.json as { sent?: boolean }).sent).toBe(false);
  expect(approvals.ok).toBe(true);
});

it("runs the five cross-department chains", async () => {
  const url = await boot();
  const stop = approver(url);
  const names = ["bug", "lead", "churn", "shipped", "signals"] as const;
  for (const name of names) {
    const response = await post(url, `/api/chains/${name}`, { timeoutMs: 8000 });
    expect(response.status, JSON.stringify(response.json)).toBe(200);
    expect(response.json.chain).toBeTruthy();
  }
  await stop();
  const events = (await fetch(new URL("/api/events?limit=200", url)).then((response) => response.json())) as {
    events: Array<{ output?: { kind?: string }; parent_id?: string }>;
  };
  expect(events.events.some((event) => event.output?.kind === "hire_needed")).toBe(true);
  expect(events.events.some((event) => event.output?.kind === "design_request")).toBe(true);
  expect(events.events.some((event) => event.parent_id)).toBe(true);
});

it("launches Pulse Studio from a product through a live listing", async () => {
  const url = await boot();
  const launched = await post(url, "/api/chains/launch", {});
  expect(launched.status, JSON.stringify(launched.json)).toBe(200);
  expect(launched.json.qa_passed).toBe(true);
  expect(launched.json.copy_mode).toBe("mock");
  const events = (await fetch(new URL("/api/events?limit=50", url)).then((response) => response.json())) as {
    events: Array<{ task_id: string; dept?: string; parent_id?: string; mode?: string; output?: { kind?: string; copy?: string; copy_mode?: string; product?: { title?: string } } }>;
  };
  const listing = events.events.find((event) => event.output?.kind === "listing_live");
  const product = events.events.find((event) => event.output?.kind === "product_created");
  expect(product?.task_id).toBe(launched.json.product_task_id);
  expect(listing?.parent_id).toBe(launched.json.page_task_id);
  expect(listing?.output?.kind).toBe("listing_live");
  const listed = listing?.output as { copy?: string; copy_mode?: string; product?: { title?: string; description?: string; sku?: string; price_usd?: number; image?: string } };
  expect(listed.product?.title).toBe("Pulse Studio");
  expect(listed.product?.description).toContain("one-page");
  expect(listed.product?.sku).toBe("pulse-studio");
  expect(listed.product?.price_usd).toBe(49);
  expect(listed.product?.image).toBeTruthy();
  expect(listed.copy).toContain("Pulse Studio");
  expect(listed.copy_mode).toBe("mock");
  expect(events.events.find((event) => event.output?.kind === "listing_live")?.mode).toBe("mock");
  expect(events.events.find((event) => event.output?.kind === "listing_live" && event.dept === "sales") ).toBeTruthy();
  const support = events.events.find((event) => event.task_id === launched.json.support_task_id && event.parent_id);
  expect(support?.parent_id).toBe(launched.json.listing_task_id);
  const page = await fetch(new URL("/pulse", url));
  const html = await page.text();
  expect(html).toContain("Pulse Studio");
  expect(html).toContain("MOCK");
});

it("turns a design listing_live webhook into sales, engineering, and support follow-ups", async () => {
  const url = await boot();
  const listed = await post(url, "/api/webhooks/inbound", {
    dept: "design",
    task_id: "design-listing-1",
    actor: "auto",
    status: "done",
    summary: "Listing live",
    mode: "mock",
    output: {
      kind: "listing_live",
      url: "/files/published/design-listing-1/index.html",
      product: { title: "Desk cactus", price_usd: 6, product_type: "sticker", tagline: "A sticker", cost_usd: 1.6, trend: "plants" },
    },
  });
  expect(listed.status).toBe(202);
  const started = Date.now();
  let events: Array<{
    dept: string;
    summary?: string;
    parent_id?: string;
    output?: { kind?: string; price?: number; title?: string; copy?: string; product?: { title?: string; description?: string; sku?: string; price_usd?: number; image?: string } };
  }> = [];
  while (Date.now() - started < 4000) {
    events = ((await fetch(new URL("/api/events?limit=80", url)).then((response) => response.json())) as { events: typeof events }).events;
    const support = events.some((event) => event.dept === "support" && event.parent_id === "design-listing-1");
    const sales = events.some((event) => event.dept === "sales" && event.output?.kind === "listing_live" && event.parent_id === "design-listing-1");
    if (support && sales) break;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  const salesListing = events.find((event) => event.dept === "sales" && event.output?.kind === "listing_live" && event.output.price === 6);
  expect(salesListing?.output?.product?.title).toBe("Desk cactus");
  expect(salesListing?.output?.product?.price_usd).toBe(6);
  expect(salesListing?.output?.product?.sku).toBe("design-listing-1");
  expect(salesListing?.output?.product?.description).toBeTruthy();
  expect(salesListing?.output?.product?.image).toContain("design-listing-1");
  expect(salesListing?.output?.title).toBe("Desk cactus");
  expect(salesListing?.output?.copy).toContain("Desk cactus");
  expect(salesListing?.summary).toContain("Desk cactus");
  expect(events.some((event) => event.dept === "engineering" && event.parent_id === "design-listing-1")).toBe(true);
  expect(events.some((event) => event.dept === "support" && event.parent_id === "design-listing-1")).toBe(true);
  expect(JSON.stringify(events)).not.toContain("@");
});

it("accepts a foreign source dept and answers only when the event is for us", async () => {
  const url = await boot();
  const finance = await post(url, "/api/webhooks/inbound", {
    dept: "finance",
    task_id: "fin-not-ours",
    actor: "dev3-finance",
    status: "needs_approval",
    summary: "Margin under the floor",
    mode: "mock",
    output: { kind: "margin_update", margin_pct: 0.1 },
  });
  expect(finance.status).toBe(200);
  expect(finance.json).toMatchObject({ ok: true, ignored: true });

  const ops = await post(url, "/api/webhooks/inbound?dept=engineering", {
    dept: "ops",
    task_id: "ops-route-1",
    actor: "dev4-ops",
    status: "done",
    summary: "Ops routed a task to engineering",
    mode: "mock",
    output: { kind: "task_routed", target_dept: "engineering" },
  });
  expect(ops.status).toBe(202);
  const started = Date.now();
  let events: Array<{ dept: string; actor?: string; parent_id?: string; output?: { kind?: string; source_dept?: string } }> = [];
  while (Date.now() - started < 4000) {
    events = ((await fetch(new URL("/api/events?limit=40", url)).then((response) => response.json())) as { events: typeof events }).events;
    if (events.some((event) => event.actor === "engineering-bot" && event.parent_id === "ops-route-1")) break;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  const ack = events.find((event) => event.actor === "engineering-bot" && event.parent_id === "ops-route-1");
  expect(ack?.dept).toBe("engineering");
  expect(ack?.output?.kind).toBe("dept_seen");
  expect(ack?.output?.source_dept).toBe("ops");
  expect(events.some((event) => event.actor === "standin-dev4")).toBe(false);

  const order = await post(url, "/api/webhooks/inbound?dept=support", {
    dept: "ops",
    task_id: "order-pulse-1",
    actor: "dev4-ops",
    status: "done",
    summary: "MOCK order placed",
    mode: "mock",
    output: { kind: "order_placed", order_id: "order-pulse-1", title: "Pulse Studio" },
  });
  expect(order.status).toBe(202);
  const supportStarted = Date.now();
  while (Date.now() - supportStarted < 4000) {
    events = ((await fetch(new URL("/api/events?limit=40", url)).then((response) => response.json())) as { events: typeof events }).events;
    if (events.some((event) => event.dept === "support" && event.parent_id === "order-pulse-1")) break;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  expect(events.some((event) => event.dept === "support" && event.actor === "support-bot" && event.parent_id === "order-pulse-1")).toBe(true);
});

it("completes an orchestrator sales task on the same task id", async () => {
  const url = await boot();
  const response = await post(url, "/api/webhooks/inbound", {
    dept: "sales",
    task_id: "sales-70885544",
    parent_id: "req-1a85a6c9",
    actor: "auto",
    status: "queued",
    summary: "Task: Draft a sales note for leads",
    mode: "live",
    output: {
      kind: "task",
      title: "Draft a sales note for leads",
      for_dept: "sales",
      detail: { text: "Draft a sales note for leads", source: "orchestrator" },
    },
  });
  expect(response.status).toBe(202);
  const started = Date.now();
  let done: { task_id?: string; parent_id?: string; status?: string; dept?: string; actor?: string; mode?: string; output?: { source?: string; request_id?: string } } | undefined;
  while (Date.now() - started < 12000) {
    const body = (await fetch(new URL("/api/events?limit=40", url)).then((res) => res.json())) as {
      events: Array<typeof done>;
    };
    done = body.events.find((event) => event?.task_id === "sales-70885544" && event.status === "done");
    if (done) break;
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  expect(done?.dept).toBe("sales");
  expect(done?.actor).toBe("sales-bot");
  expect(done?.parent_id).toBe("req-1a85a6c9");
  expect(done?.output?.source).toBe("orchestrator");
  expect(done?.output?.request_id).toBe("req-1a85a6c9");
  expect(done?.mode).toBe("mock");

  const ignored = await post(url, "/api/webhooks/inbound", {
    dept: "finance",
    task_id: "finance-skip",
    actor: "auto",
    status: "queued",
    summary: "Not our dept",
    mode: "mock",
    output: { kind: "task", detail: { source: "orchestrator", text: "margin" }, for_dept: "finance" },
  });
  expect(ignored.status).toBe(200);
  expect(ignored.json).toMatchObject({ ok: true, ignored: true });
});

it("returns 202 while a lead chain waits for the founder", async () => {
  const url = await boot();
  const response = await post(url, "/api/chains/lead", { timeoutMs: 300 });
  expect(response.status).toBe(202);
  expect(response.json.status).toBe("awaiting_founder");
  expect(typeof response.json.task_id).toBe("string");
});

it("serves one MCP endpoint, the panel, and a 10s poll fallback", async () => {
  expect(POLL_FALLBACK_MS).toBeGreaterThanOrEqual(10_000);
  const url = await boot();
  const listed = await post(url, "/mcp", { jsonrpc: "2.0", id: 1, method: "tools/list" });
  const tools = (listed.json as { result: { tools: Array<{ name: string }> } }).result.tools.map((tool) => tool.name);
  expect(tools).toEqual(expect.arrayContaining(["sales.find_leads", "sales.draft_outreach", "support.triage", "support.draft_reply", "eng.plan_issue"]));
  const call = await post(url, "/mcp", {
    jsonrpc: "2.0",
    id: 2,
    method: "tools/call",
    params: { name: "eng.plan_issue", arguments: {} },
  });
  expect(call.status).toBe(200);
  expect(JSON.stringify(call.json)).toContain("hire_needed");
  const panel = await fetch(new URL("/panel", url));
  const html = await panel.text();
  expect(html).toContain("Sales");
  expect(html).toContain("Support");
  expect(html).toContain("Engineering");
  const health = (await fetch(new URL("/health", url)).then((response) => response.json())) as { ok: boolean; modes: { qa: string } };
  expect(health.ok).toBe(true);
  expect(health.modes.qa).toBe("rules_only");
  const dashboard = await fetch(new URL("/dashboard", url));
  expect(dashboard.status).toBe(200);
});
