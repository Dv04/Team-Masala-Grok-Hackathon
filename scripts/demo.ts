import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createApp, listen } from "../src/server.js";

const started = Date.now();
const dir = await mkdtemp(join(tmpdir(), "dev2-demo-"));
const remote = process.env.DEPARTMENTS_BASE_URL?.trim();
let url = "";
const app = createApp({
  dataDir: dir,
  mode: remote ? "live" : "mock",
  getSelfUrl: () => url,
  getDepartmentsUrl: () => remote || url,
  getDashboardUrl: () => process.env.DASHBOARD_BASE_URL?.trim() || remote || url,
});
url = await listen(app.server, Number(process.env.WEBHOOK_PORT ?? 8811));
console.log(`dev2 ${url}`);
console.log(`panel ${url}/panel`);
console.log(`departments ${process.env.DEPARTMENTS_BASE_URL?.trim() || url}`);

let stopApproval = false;
const approver = (async () => {
  const target = process.env.DEPARTMENTS_BASE_URL?.trim() || url;
  while (!stopApproval) {
    try {
      const response = await fetch(new URL("/api/approvals?pending=true", target));
      const body = (await response.json()) as { pending?: Array<{ task_id: string; dept?: string }> };
      for (const item of body.pending ?? []) {
        if (item.dept && item.dept !== "sales" && item.dept !== "support" && item.dept !== "engineering") continue;
        await fetch(new URL(`/api/approvals/${item.task_id}`, target), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ decision: "approved", note: "demo" }),
        });
        console.log(`approved ${item.task_id}`);
      }
    } catch {
      // The queue may be briefly empty while a draft is still running.
    }
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
})();

async function call(path: string, body: unknown = {}) {
  const response = await fetch(new URL(path, url), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = (await response.json()) as Record<string, unknown>;
  if (!response.ok) throw new Error(`${path} ${response.status} ${JSON.stringify(json)}`);
  console.log(path, JSON.stringify(json).slice(0, 240));
  return json;
}

await call("/api/sales/find-leads", { icp: "independent coffee roasters in Austin", limit: 2 });
await call("/api/support/triage");
await call("/api/support/draft-reply", { message_id: "msg_ship" });
await call("/api/engineering/plan-issue");
await call("/api/chains/bug");
await call("/api/chains/lead", { timeoutMs: 15000 });
await call("/api/chains/signals");
await call("/api/chains/launch");

const log = (await fetch(new URL("/api/events?limit=12", url)).then((response) => response.json())) as {
  events: Array<{ dept: string; status: string; summary: string }>;
};
console.log("--- latest events ---");
for (const event of log.events) console.log(`${event.dept} ${event.status} ${event.summary}`);

stopApproval = true;
await approver;
await new Promise<void>((resolve, reject) => app.server.close((error) => (error ? reject(error) : resolve())));
await rm(dir, { recursive: true, force: true });
console.log(`demo finished in ${Date.now() - started}ms`);
