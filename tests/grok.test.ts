import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { configuredCopyMode, GROK_MOCK_TEXT, grokText, resetGrokBudget } from "../src/grok.js";
import { createApp, listen } from "../src/server.js";

const originalFetch = globalThis.fetch;
const envKeys = ["XAI_API_KEY", "XAI_BASE_URL", "XAI_BUDGET_USD", "XAI_MODEL"] as const;
const savedEnv = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]));

afterEach(() => {
  globalThis.fetch = originalFetch;
  resetGrokBudget();
  for (const key of envKeys) {
    if (savedEnv[key] === undefined) delete process.env[key];
    else process.env[key] = savedEnv[key];
  }
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

it("stays mock without an xai- key and calls the configured base with a small token cap", async () => {
  expect(configuredCopyMode()).toBe("mock");
  expect(await grokText("hello")).toEqual({ text: GROK_MOCK_TEXT, mode: "mock" });

  process.env.XAI_API_KEY = "not-a-live-key";
  expect(configuredCopyMode()).toBe("mock");

  process.env.XAI_BASE_URL = "https://grok.example.test/v1";
  expect(configuredCopyMode()).toBe("live");

  let seen: { url: string; body: Record<string, unknown>; authorization: string } | undefined;
  globalThis.fetch = (async (input, init) => {
    seen = {
      url: String(input),
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
      authorization: new Headers(init?.headers).get("authorization") ?? "",
    };
    return jsonResponse({ output_text: "Desk cactus is $6." });
  }) as typeof fetch;

  const result = await grokText("Write copy for Desk cactus at $6", {
    system: "You write sales copy.",
    maxOutputTokens: 200,
  });
  expect(result).toEqual({ text: "Desk cactus is $6.", mode: "live" });
  expect(seen?.url).toBe("https://grok.example.test/v1/responses");
  expect(seen?.authorization).toBe("Bearer not-a-live-key");
  expect(seen?.body.max_output_tokens).toBe(200);
  expect(seen?.body.input).toEqual([
    { role: "system", content: "You write sales copy." },
    { role: "user", content: "Write copy for Desk cactus at $6" },
  ]);

  delete process.env.XAI_BASE_URL;
  process.env.XAI_API_KEY = "xai-test-key";
  expect(configuredCopyMode()).toBe("live");
});

it("logs the status and message on an xAI error and never the key", async () => {
  const key = "xai-supersecretkeyvalue1234567890";
  process.env.XAI_API_KEY = key;
  const warnings: string[] = [];
  const warn = console.warn;
  console.warn = (...args: unknown[]) => {
    warnings.push(args.map(String).join(" "));
  };
  globalThis.fetch = (async () =>
    jsonResponse({ error: { message: `Incorrect API key ${key} provided` } }, 401)) as typeof fetch;
  try {
    const result = await grokText("hi");
    expect(result).toEqual({ text: GROK_MOCK_TEXT, mode: "mock" });
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("xAI error 401:");
    expect(warnings[0]).toContain("Incorrect API key");
    expect(warnings[0]).not.toContain(key);
    expect(warnings[0]).not.toContain("supersecret");
  } finally {
    console.warn = warn;
  }
});

it("stops calling xAI once XAI_BUDGET_USD is spent", async () => {
  process.env.XAI_API_KEY = "xai-budget-key";
  process.env.XAI_BUDGET_USD = "1";
  let calls = 0;
  globalThis.fetch = (async () => {
    calls += 1;
    return jsonResponse({ output_text: "ok", usage: { cost_in_usd_ticks: 20_000_000_000 } });
  }) as typeof fetch;
  expect((await grokText("first")).mode).toBe("live");
  expect((await grokText("second")).mode).toBe("mock");
  expect(calls).toBe(1);

  resetGrokBudget();
  process.env.XAI_BUDGET_USD = "0";
  expect((await grokText("blocked")).mode).toBe("mock");
  expect(calls).toBe(1);
});

it("answers hub and orchestrator tasks with Grok and falls back to the template", async () => {
  const dir = await mkdtemp(join(tmpdir(), "dev2-grok-"));
  let url = "";
  const app = createApp({
    dataDir: dir,
    mode: "mock",
    getSelfUrl: () => url,
    getDepartmentsUrl: () => url,
    getDashboardUrl: () => url,
  });
  url = await listen(app.server, 0);
  const key = "xai-live-listing-key";
  process.env.XAI_API_KEY = key;
  const prompts: string[] = [];
  let hang = false;
  globalThis.fetch = (async (input, init) => {
    const target = String(input);
    if (!target.includes("/responses")) return originalFetch(input, init);
    const body = JSON.parse(String(init?.body)) as { input?: Array<{ content?: string }> };
    const user = body.input?.map((item) => item.content ?? "").join("\n") ?? "";
    prompts.push(user);
    if (hang) {
      return new Promise((_resolve, reject) => {
        const abort = () => reject(Object.assign(new Error("The operation was aborted"), { name: "AbortError" }));
        if (init?.signal?.aborted) {
          abort();
          return;
        }
        init?.signal?.addEventListener("abort", abort, { once: true });
      });
    }
    return jsonResponse({ output_text: user.includes("Desk cactus") ? "Desk cactus is listed at $6." : "Grok says the order shipped." });
  }) as typeof fetch;

  try {
    const listed = await fetch(new URL("/api/webhooks/inbound", url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dept: "design",
        task_id: "design-live-1",
        actor: "auto",
        status: "done",
        summary: "Listing live",
        mode: "mock",
        output: {
          kind: "listing_live",
          url: "/files/published/design-live-1/index.html",
          product: { title: "Desk cactus", price_usd: 6 },
        },
      }),
    });
    expect(listed.status).toBe(202);

    const shipped = await fetch(new URL("/api/webhooks/inbound", url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dept: "support",
        task_id: "hub-ship-1",
        actor: "auto",
        status: "queued",
        summary: "Task: where is my order",
        mode: "live",
        parent_id: "orch-1",
        output: { kind: "task", title: "where is my order", detail: { text: "shipping update please" } },
      }),
    });
    expect(shipped.status).toBe(202);

    const refund = await fetch(new URL("/api/tasks", url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        for_dept: "support",
        title: "Please refund order 1001",
        detail: "The mug arrived cracked",
        source: "orchestrator",
        parent_id: "orch-2",
      }),
    });
    expect(refund.status).toBe(201);

    const health = (await fetch(new URL("/health", url)).then((response) => response.json())) as {
      mode: string;
      modes: { sales: string };
      depts: Array<{ mode: string }>;
    };
    expect(health.mode).toBe("live");
    expect(health.modes.sales).toBe("live");
    expect(health.depts.every((dept) => dept.mode === "live")).toBe(true);

    const started = Date.now();
    let events: Array<{ dept: string; task_id: string; status: string; summary: string; parent_id?: string; output?: Record<string, unknown> }> = [];
    while (Date.now() - started < 4000) {
      events = ((await fetch(new URL("/api/events?limit=80", url)).then((response) => response.json())) as { events: typeof events }).events;
      const sales = events.some((event) => event.dept === "sales" && event.output?.copy_mode === "live");
      const ship = events.some((event) => event.task_id === "hub-ship-1" && event.status === "done");
      const money = events.some((event) => event.summary.includes("refund") && event.status === "done");
      if (sales && ship && money) break;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }

    const sales = events.find((event) => event.dept === "sales" && event.output?.kind === "listing_live");
    const engineering = events.find((event) => event.dept === "engineering" && event.output?.kind === "listing_live");
    expect(sales?.output?.copy).toBe("Desk cactus is listed at $6.");
    expect(sales?.output?.copy_mode).toBe("live");
    expect(engineering?.output?.copy_mode).toBe("live");
    expect(prompts.some((prompt) => prompt.includes("Desk cactus") && prompt.includes("$6"))).toBe(true);

    const ship = events.find((event) => event.task_id === "hub-ship-1" && event.status === "done");
    expect(ship?.output?.kind).toBe("shipping question");
    expect(ship?.output?.answer).toBe("Grok says the order shipped.");
    expect(ship?.output?.copy_mode).toBe("live");
    expect(ship?.parent_id).toBe("orch-1");
    expect(ship?.summary).toBe("support done shipping question: where is my order");

    const money = events.find((event) => event.status === "done" && event.output?.kind === "refund");
    expect(money?.output?.answer).toBe("Grok says the order shipped.");
    expect(money?.output?.copy_mode).toBe("live");
    expect(money?.summary).toContain("support done refund:");

    hang = true;
    const slow = await fetch(new URL("/api/webhooks/inbound", url), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dept: "engineering",
        task_id: "hub-slow-1",
        actor: "auto",
        status: "queued",
        summary: "Task: timeout",
        mode: "mock",
        output: { kind: "task", title: "Retry the worker", detail: "It is stuck" },
      }),
    });
    expect(slow.status).toBe(202);
    const slowStarted = Date.now();
    let fallback: (typeof events)[number] | undefined;
    while (Date.now() - slowStarted < 6000) {
      events = ((await fetch(new URL("/api/events?limit=80", url)).then((response) => response.json())) as { events: typeof events }).events;
      fallback = events.find((event) => event.task_id === "hub-slow-1" && event.status === "done");
      if (fallback) break;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    expect(fallback?.summary).toBe("engineering done issue: Retry the worker");
    expect(fallback?.output?.answer).toBe("engineering done issue: Retry the worker");
    expect(fallback?.output?.copy_mode).toBe("mock");
  } finally {
    await new Promise<void>((resolve, reject) => app.server.close((error) => (error ? reject(error) : resolve())));
    await rm(dir, { recursive: true, force: true });
  }
});
