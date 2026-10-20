import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, expect, it } from "vitest";
import { DepartmentClient } from "../src/contract/client.js";
import { runCustomerGate } from "../src/contract/gate.js";
import { followEventStream } from "../src/contract/client.js";
import { createApp, listen, registerWebhooks } from "../src/server.js";

const timings: Array<{ check: string; ms: number; pass: boolean }> = [];

async function liveBase(): Promise<string | null> {
  try {
    const response = await fetch("http://127.0.0.1:8810/health", { signal: AbortSignal.timeout(800) });
    if (!response.ok) return null;
    const body = (await response.json()) as { service?: string };
    return body.service === "dev4-departments" ? "http://127.0.0.1:8810" : null;
  } catch {
    return null;
  }
}

const base = await liveBase();
const dir = base ? await mkdtemp(join(tmpdir(), "dev2-verify-")) : "";
let self = "";
const app = base
  ? createApp({
      dataDir: dir,
      mode: "live",
      getSelfUrl: () => self,
      getDepartmentsUrl: () => base,
      getDashboardUrl: () => base,
    })
  : null;
const feed = new AbortController();
if (app && base) {
  self = await listen(app.server, 0);
  void followEventStream(base, app.hub, feed.signal);
  await registerWebhooks(base, self);
}

afterAll(async () => {
  if (!app) return;
  feed.abort();
  await new Promise<void>((resolve, reject) => app.server.close((error) => (error ? reject(error) : resolve())));
  if (dir) await rm(dir, { recursive: true, force: true });
  console.log("\nLIVE CHECKS");
  for (const row of timings) console.log(`${row.pass ? "PASS" : "FAIL"}\t${row.ms}ms\t${row.check}`);
});

async function timed<T>(check: string, run: () => Promise<T>): Promise<T> {
  const started = Date.now();
  try {
    const value = await run();
    timings.push({ check, ms: Date.now() - started, pass: true });
    return value;
  } catch (error) {
    timings.push({ check, ms: Date.now() - started, pass: false });
    throw error;
  }
}

async function post(path: string, body: unknown) {
  const response = await fetch(new URL(path, self), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = (await response.json()) as Record<string, unknown>;
  if (!response.ok) throw new Error(`${path} ${response.status} ${JSON.stringify(json)}`);
  return json;
}

function approver() {
  if (!base) return async () => undefined;
  let stop = false;
  const loop = (async () => {
    while (!stop) {
      const response = await fetch(new URL("/api/approvals?pending=true", base));
      const body = (await response.json()) as { pending?: Array<{ task_id: string; dept?: string }> };
      for (const item of body.pending ?? []) {
        if (item.dept && !["sales", "support", "engineering"].includes(item.dept)) continue;
        await fetch(new URL(`/api/approvals/${item.task_id}`, base), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ decision: "approved", note: "verify" }),
        });
      }
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
  })();
  return async () => {
    stop = true;
    await loop;
  };
}

it.skipIf(!base)("exercises every tool, chain, and Pulse handoff on the real departments service", async () => {
  if (!base || !app) return;
  const stop = approver();
  try {
    const mcpTools = ["sales.find_leads", "sales.draft_outreach", "support.triage", "support.draft_reply", "eng.plan_issue"] as const;
    const rest: Array<[string, string, unknown]> = [
      ["sales.find_leads", "/api/sales/find-leads", { limit: 1 }],
      ["sales.draft_outreach", "/api/sales/draft-outreach", { limit: 1 }],
      ["support.triage", "/api/support/triage", {}],
      ["support.draft_reply ship", "/api/support/draft-reply", { message_id: "msg_ship" }],
      ["support.draft_reply refund", "/api/support/draft-reply", { message_id: "msg_refund" }],
      ["eng.plan_issue", "/api/engineering/plan-issue", {}],
    ];
    for (const [name, path, body] of rest) await timed(`REST ${name}`, () => post(path, body));
    for (const name of mcpTools) {
      await timed(`MCP ${name}`, () =>
        post("/mcp", { jsonrpc: "2.0", id: name, method: "tools/call", params: { name, arguments: name === "sales.find_leads" ? { limit: 1 } : {} } }),
      );
    }
    for (const chain of ["bug", "lead", "churn", "shipped", "signals", "launch"] as const) {
      await timed(`chain ${chain}`, () => post(`/api/chains/${chain}`, { timeoutMs: 8000 }));
    }

    const support = new DepartmentClient({ baseUrl: base, dept: "support", mode: "live", hub: app.hub, actor: "support-bot" });
    const revised = await timed("QA fail then revise once", () =>
      runCustomerGate({
        client: support,
        taskId: `pii-revise-${Date.now()}`,
        kind: "customer_reply",
        content: "Thanks for the note. [TODO] I will send the shipping update shortly.",
        summary: "Revise a placeholder reply",
        timeoutMs: 8000,
      }),
    );
    expect(revised.verdict).toBe("pass");
    expect(revised.sent).toBe(true);

    await timed("PII stays out of the event log", async () => {
      const taskId = `pii-${Date.now()}`;
      await support.log({
        task_id: taskId,
        status: "done",
        summary: "Contact ada@secretmail.com about 123-45-6789",
        output: { note: "card 4242424242424242 and ada@secretmail.com" },
      });
      const events = await support.listEvents({ task_id: taskId, dept: "" });
      const blob = JSON.stringify(events);
      expect(blob).not.toContain("ada@secretmail.com");
      expect(blob).not.toContain("123-45-6789");
      expect(blob).not.toContain("4242424242424242");
      expect(blob).toContain("[redacted]");
    });

    const pulse = await timed("POST /api/pulse/start reaches our bots", async () => {
      const response = await fetch(new URL("/api/pulse/start", base), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ trend: "Desk cactus club", product_type: "sticker", source: "manual" }),
      });
      const body = (await response.json()) as { trend_task?: string; ok?: boolean };
      expect(response.ok).toBe(true);
      const root = body.trend_task;
      expect(root).toBeTruthy();
      const started = Date.now();
      let sales = false;
      let engineering = false;
      let supportHit = false;
      while (Date.now() - started < 12000) {
        const events = (await fetch(new URL("/api/events?limit=400", base)).then((item) => item.json())) as {
          events: Array<{ task_id?: string; dept: string; parent_id?: string; actor?: string; output?: { kind?: string; listing_task?: string } }>;
        };
        const design = events.events.find((event) => event.dept === "design" && event.parent_id === root && event.output?.kind === "listing_live");
        if (design?.task_id) {
          const follows = (event: { dept: string; actor?: string; parent_id?: string; output?: { listing_task?: string } }) =>
            event.actor !== "standin-dev4" && (event.parent_id === design.task_id || event.output?.listing_task === design.task_id);
          sales = events.events.some((event) => event.dept === "sales" && follows(event));
          engineering = events.events.some((event) => event.dept === "engineering" && follows(event));
          supportHit = events.events.some((event) => event.dept === "support" && follows(event));
          if (sales && engineering && supportHit) return events.events.filter((event) => event.parent_id === root || event.parent_id === design.task_id).length;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      throw new Error(`pulse follow-up missing sales=${sales} engineering=${engineering} support=${supportHit}`);
    });
    expect(pulse).toBeGreaterThan(0);

    const dashboard = await timed("dashboard has parent links", async () => {
      const page = await fetch(new URL("/dashboard", base));
      expect(page.status).toBe(200);
      const events = (await fetch(new URL("/api/events?limit=400", base)).then((response) => response.json())) as {
        events: Array<{ dept: string; mode?: string; parent_id?: string; status?: string }>;
      };
      for (const dept of ["sales", "support", "engineering"]) {
        expect(events.events.some((event) => event.dept === dept && event.mode === "live")).toBe(true);
      }
      expect(events.events.some((event) => event.parent_id)).toBe(true);
      return page.status;
    });
    expect(dashboard).toBe(200);

    const slow = timings.filter((row) => row.ms > 1000);
    console.log(`slow (>1s): ${slow.map((row) => `${row.check} ${row.ms}ms`).join(", ") || "none"}`);
  } finally {
    await stop();
  }
}, 60000);
