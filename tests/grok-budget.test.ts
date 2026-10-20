import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it, vi } from "vitest";
import { grokText } from "../src/grok.js";

const saved = {
  XAI_API_KEY: process.env.XAI_API_KEY,
  XAI_BUDGET_USD: process.env.XAI_BUDGET_USD,
  XAI_BUDGET_PATH: process.env.XAI_BUDGET_PATH,
  XAI_MODEL: process.env.XAI_MODEL,
  XAI_BASE_URL: process.env.XAI_BASE_URL,
  XAI_MAX_OUTPUT_TOKENS: process.env.XAI_MAX_OUTPUT_TOKENS,
};

afterEach(() => {
  vi.restoreAllMocks();
  for (const [key, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

it("keeps Grok labeled MOCK without an xai- key and under the budget cap", async () => {
  const dir = await mkdtemp(join(tmpdir(), "xai-budget-"));
  try {
    delete process.env.XAI_API_KEY;
    const plain = await grokText("hello");
    expect(plain.mode).toBe("mock");
    expect(plain.text.startsWith("MOCK Grok:")).toBe(true);

    process.env.XAI_API_KEY = "not-a-real-key";
    const wrong = await grokText("hello");
    expect(wrong.mode).toBe("mock");

    process.env.XAI_API_KEY = "xai-test";
    process.env.XAI_BUDGET_USD = "0.0000001";
    process.env.XAI_BUDGET_PATH = join(dir, "budget.json");
    process.env.XAI_MAX_OUTPUT_TOKENS = "120";
    delete process.env.XAI_MODEL;
    delete process.env.XAI_BASE_URL;
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const capped = await grokText("Write one sentence about Pulse Studio");
    expect(capped.mode).toBe("mock");
    expect(capped.text).toContain("MOCK Grok:");
    expect(capped.text.toLowerCase()).toContain("budget");
    expect(fetchSpy).not.toHaveBeenCalled();

    process.env.XAI_BUDGET_USD = "2";
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ output_text: "Pulse Studio is a one-page site.", usage: { input_tokens: 12, output_tokens: 9 } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const live = await grokText("hi");
    expect(live.mode).toBe("live");
    expect(live.text).toBe("Pulse Studio is a one-page site.");
    const call = fetchSpy.mock.calls[0];
    expect(String(call?.[0])).toBe("https://api.x.ai/v1/responses");
    const sent = JSON.parse(String((call?.[1] as RequestInit).body));
    expect(sent.model).toBe("grok-4.3");
    expect(sent.max_output_tokens).toBe(120);
    const ledger = JSON.parse(await readFile(join(dir, "budget.json"), "utf8")) as { spent_usd: number };
    expect(ledger.spent_usd).toBeGreaterThan(0);
    expect(ledger.spent_usd).toBeLessThan(2);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

it("warns once on an xAI error and asks for about 200 tokens", async () => {
  const dir = await mkdtemp(join(tmpdir(), "xai-error-"));
  try {
    const key = "xai-supersecretkeyvalue";
    process.env.XAI_API_KEY = key;
    process.env.XAI_BUDGET_USD = "2";
    process.env.XAI_BUDGET_PATH = join(dir, "budget.json");
    process.env.XAI_BASE_URL = "https://proxy.example/v1";
    delete process.env.XAI_MAX_OUTPUT_TOKENS;
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: { message: `overloaded ${key}` } }), { status: 503 }),
    );
    const failed = await grokText("Write a listing sentence");
    expect(failed.mode).toBe("mock");
    expect(failed.text.startsWith("MOCK Grok:")).toBe(true);
    expect(String(fetchSpy.mock.calls[0]?.[0])).toBe("https://proxy.example/v1/responses");
    const sent = JSON.parse(String((fetchSpy.mock.calls[0]?.[1] as RequestInit).body));
    expect(sent.max_output_tokens).toBe(200);
    expect(warn).toHaveBeenCalledTimes(1);
    const line = String(warn.mock.calls[0]?.[0]);
    expect(line).toContain("503");
    expect(line).toContain("overloaded");
    expect(line).not.toContain(key);

    fetchSpy.mockImplementation((_url, init) => {
      return new Promise((_resolve, reject) => {
        const signal = (init as RequestInit | undefined)?.signal;
        const fail = () => {
          const error = new Error("The operation was aborted due to timeout");
          error.name = "TimeoutError";
          reject(error);
        };
        if (signal?.aborted) fail();
        else signal?.addEventListener("abort", fail, { once: true });
      });
    });
    const timed = await grokText("slow", { timeoutMs: 40 });
    expect(timed.mode).toBe("mock");
    expect(warn).toHaveBeenCalledTimes(2);
    expect(String(warn.mock.calls[1]?.[0])).toContain("408");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
