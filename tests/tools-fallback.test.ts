import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { createSalesAdapters } from "../src/sales/adapters.js";
import { useSalesAdapters } from "../src/sales/bot.js";
import { createApp, listen } from "../src/server.js";

const running: Array<{ close: () => Promise<void>; dir: string }> = [];

afterEach(async () => {
  useSalesAdapters(createSalesAdapters());
  while (running.length) {
    const item = running.pop();
    if (!item) break;
    await item.close();
    await rm(item.dir, { recursive: true, force: true });
  }
});

it("finishes a sales inbound task when live tools have no OpenOutreach binary", async () => {
  const previousMode = process.env.TOOLS_MODE;
  const previousBin = process.env.OPENOUTREACH_BIN;
  process.env.TOOLS_MODE = "live";
  delete process.env.OPENOUTREACH_BIN;
  const adapters = createSalesAdapters({ toolsMode: "live" });
  useSalesAdapters(adapters);
  const found = await adapters.openoutreach.find("independent coffee roasters", 1);
  expect(found.mode).toBe("mock");
  expect(found.length).toBeGreaterThan(0);

  const dir = await mkdtemp(join(tmpdir(), "dev2-fallback-"));
  let url = "";
  const app = createApp({
    dataDir: dir,
    mode: "live",
    getSelfUrl: () => url,
    getDepartmentsUrl: () => url,
    getDashboardUrl: () => url,
  });
  url = await listen(app.server, 0);
  running.push({
    close: () =>
      new Promise<void>((resolve, reject) => {
        app.server.close((error) => (error ? reject(error) : resolve()));
      }),
    dir,
  });

  try {
    const response = await fetch(new URL("/api/webhooks/inbound", url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dept: "sales",
        task_id: "sales-live-fallback",
        parent_id: "req-fallback",
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
      }),
    });
    expect(response.status).toBe(202);

    const started = Date.now();
    let done: { status?: string; dept?: string; mode?: string; task_id?: string } | undefined;
    let listed = false;
    while (Date.now() - started < 12000) {
      const body = (await fetch(new URL("/api/events?limit=80", url)).then((res) => res.json())) as {
        events: Array<{ status?: string; dept?: string; mode?: string; task_id?: string; summary?: string }>;
      };
      done = body.events.find((event) => event.task_id === "sales-live-fallback" && event.status === "done");
      listed = body.events.some((event) => event.summary?.includes("Built a lead list"));
      if (done && listed) break;
      await new Promise((resolve) => setTimeout(resolve, 40));
    }
    expect(listed).toBe(true);
    expect(done?.dept).toBe("sales");
    expect(done?.status).toBe("done");
  } finally {
    if (previousMode === undefined) delete process.env.TOOLS_MODE;
    else process.env.TOOLS_MODE = previousMode;
    if (previousBin === undefined) delete process.env.OPENOUTREACH_BIN;
    else process.env.OPENOUTREACH_BIN = previousBin;
  }
});
