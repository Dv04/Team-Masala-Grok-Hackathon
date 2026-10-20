import { createServer } from "node:http";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { createApp, listen, registerWebhooks } from "../src/server.js";
import { liveSuitesEnabled } from "./live-gate.js";

async function liveDepartments(): Promise<string | null> {
  if (!liveSuitesEnabled()) return null;
  const candidates = [process.env.DEPARTMENTS_BASE_URL?.trim(), "http://127.0.0.1:8810"].filter(
    (value): value is string => Boolean(value),
  );
  for (const base of candidates) {
    try {
      const response = await fetch(new URL("/health", base), { signal: AbortSignal.timeout(800) });
      if (!response.ok) continue;
      const body = (await response.json()) as { service?: string };
      if (body.service === "dev4-departments") return base.replace(/\/$/, "");
    } catch {
      // The departments service is not running. The suite still passes.
    }
  }
  return null;
}

const base = await liveDepartments();

it.skipIf(!base)("registers a sales webhook, logs an event, and receives the founder approval", async () => {
  if (!base) return;
  const seen: Array<{ actor?: string; status?: string; task_id?: string }> = [];
  const hook = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      try {
        seen.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        // Ignore non-JSON probes.
      }
      res.end("{}");
    });
  });
  hook.listen(0, "127.0.0.1");
  await once(hook, "listening");
  const address = hook.address();
  if (!address || typeof address === "string") throw new Error("webhook did not bind");
  const hookUrl = `http://127.0.0.1:${address.port}/sales`;
  const taskId = `dev2-live-${Date.now()}`;
  try {
    const registered = await fetch(new URL("/api/webhooks", base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: hookUrl, dept: "sales" }),
    });
    expect(registered.ok).toBe(true);

    const logged = await fetch(new URL("/api/events", base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dept: "sales",
        task_id: taskId,
        actor: "dev2-bot",
        status: "needs_approval",
        summary: "Dev2 live check: first-touch email is waiting",
        mode: "mock",
        needs_approval: true,
        output: { kind: "outbound_email", sent: false },
      }),
    });
    expect(logged.ok).toBe(true);

    const approved = await fetch(new URL(`/api/approvals/${taskId}`, base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision: "approved", note: "dev2 integration" }),
    });
    expect(approved.ok).toBe(true);

    const started = Date.now();
    while (!seen.some((event) => event.task_id === taskId && event.actor === "founder" && event.status === "approved")) {
      if (Date.now() - started > 5000) break;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    expect(seen.some((event) => event.task_id === taskId && event.actor === "founder" && event.status === "approved")).toBe(true);
  } finally {
    await new Promise<void>((resolve, reject) => hook.close((error) => (error ? reject(error) : resolve())));
  }
});

it.skipIf(!base)("connects sales, support, and engineering to the real dashboard", async () => {
  if (!base) return;
  const dir = await mkdtemp(join(tmpdir(), "dev2-live-"));
  let self = "";
  const app = createApp({
    dataDir: dir,
    getSelfUrl: () => self,
    getDepartmentsUrl: () => base,
    getDashboardUrl: () => base,
  });
  self = await listen(app.server, 0);
  try {
    await registerWebhooks(base, self);
    const hooks = (await fetch(new URL("/api/webhooks", base)).then((response) => response.json())) as {
      webhooks?: Array<{ dept?: string; url?: string }>;
    };
    for (const dept of ["sales", "support", "engineering"]) {
      expect(hooks.webhooks?.some((hook) => hook.dept === dept && hook.url?.startsWith(self))).toBe(true);
    }
    for (const [path, body] of [
      ["/api/sales/find-leads", { limit: 1, icp: "pulse studio buyers" }],
      ["/api/support/triage", {}],
      ["/api/engineering/plan-issue", {}],
      ["/api/chains/launch", {}],
    ] as const) {
      const response = await fetch(new URL(path, self), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await response.json();
      expect(response.ok, `${path} ${JSON.stringify(json)}`).toBe(true);
    }
    const events = (await fetch(new URL("/api/events?limit=400", base)).then((response) => response.json())) as {
      events: Array<{ dept: string; summary?: string; output?: { kind?: string } }>;
    };
    for (const dept of ["sales", "support", "engineering"]) {
      expect(events.events.some((event) => event.dept === dept)).toBe(true);
    }
    expect(events.events.some((event) => event.output?.kind === "listing_live")).toBe(true);
    expect(events.events.some((event) => event.output?.kind === "product_created")).toBe(true);
    const dashboard = await fetch(new URL("/dashboard", base));
    expect(dashboard.status).toBe(200);
    const html = await dashboard.text();
    expect(html).toContain('key:"sales"');
    expect(html).toContain('key:"support"');
    expect(html).toContain('key:"engineering"');
    const tileDepts = new Set(events.events.map((event) => event.dept));
    expect(["sales", "support", "engineering"].every((dept) => tileDepts.has(dept))).toBe(true);
  } finally {
    await new Promise<void>((resolve, reject) => app.server.close((error) => (error ? reject(error) : resolve())));
    await rm(dir, { recursive: true, force: true });
  }
}, 40000);
