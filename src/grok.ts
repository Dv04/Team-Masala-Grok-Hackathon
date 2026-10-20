import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

/** Canned Grok reply. Shown until XAI_API_KEY is set; the same function then calls the live API. */
export const GROK_MOCK_TEXT =
  "MOCK Grok: Pulse Studio is a one-page product site for a small team. It explains the product and points buyers to support. No model wrote this sentence.";

const DEFAULT_BASE = "https://api.x.ai/v1";
const DEFAULT_MODEL = "grok-4.3";
const DEFAULT_BUDGET_USD = 2;
const DEFAULT_MAX_OUTPUT = 200;

/** Published grok-4.3 short-context rates, USD per 1M tokens. Estimates; override with XAI_PRICE_*_PER_M. */
const DEFAULT_PRICE_INPUT = 1.25;
const DEFAULT_PRICE_CACHED = 0.2;
const DEFAULT_PRICE_OUTPUT = 2.5;

function num(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function budgetFile(): string {
  return process.env.XAI_BUDGET_PATH?.trim() || path.join(process.cwd(), "data", "xai-budget.json");
}

async function spentUsd(): Promise<number> {
  try {
    const raw = JSON.parse(await readFile(budgetFile(), "utf8")) as { spent_usd?: unknown };
    return typeof raw.spent_usd === "number" && Number.isFinite(raw.spent_usd) ? raw.spent_usd : 0;
  } catch {
    return 0;
  }
}

async function addSpent(amount: number): Promise<number> {
  const next = (await spentUsd()) + amount;
  const file = budgetFile();
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, JSON.stringify({ spent_usd: next, updated: new Date().toISOString() }));
  return next;
}

function prices(): { input: number; cached: number; output: number } {
  return {
    input: num(process.env.XAI_PRICE_INPUT_PER_M, DEFAULT_PRICE_INPUT),
    cached: num(process.env.XAI_PRICE_CACHED_PER_M, DEFAULT_PRICE_CACHED),
    output: num(process.env.XAI_PRICE_OUTPUT_PER_M, DEFAULT_PRICE_OUTPUT),
  };
}

/** Conservative pre-call estimate so a call that would cross the cap is not sent. */
export function estimateCallUsd(prompt: string, maxOutputTokens: number): number {
  const rate = prices();
  const inputTokens = Math.ceil(prompt.length / 4);
  return (inputTokens * rate.input + maxOutputTokens * rate.output) / 1_000_000;
}

function mock(note?: string): { text: string; mode: "mock"; note?: string } {
  const text = note ? `${GROK_MOCK_TEXT} ${note}` : GROK_MOCK_TEXT;
  return note ? { text, mode: "mock", note } : { text, mode: "mock" };
}

function warnXai(status: number, message: string, key: string): void {
  let text = message || "xAI request failed";
  if (key) text = text.split(key).join("[redacted]");
  text = text.replace(/Bearer\s+\S+/gi, "Bearer [redacted]");
  text = text.replace(/\s+/g, " ").trim().slice(0, 240);
  console.warn(`xAI ${status}: ${text || "xAI request failed"}`);
}

async function xaiErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string }; message?: string };
    return body.error?.message || body.message || response.statusText || "xAI request failed";
  } catch {
    return response.statusText || "xAI request failed";
  }
}

export async function grokText(
  prompt: string,
  options: { timeoutMs?: number } = {},
): Promise<{ text: string; mode: "live" | "mock"; note?: string }> {
  const key = process.env.XAI_API_KEY?.trim() ?? "";
  if (!key.startsWith("xai-")) return mock();
  const cap = num(process.env.XAI_BUDGET_USD, DEFAULT_BUDGET_USD);
  const maxOutput = Math.max(16, Math.floor(num(process.env.XAI_MAX_OUTPUT_TOKENS, DEFAULT_MAX_OUTPUT)));
  const spent = await spentUsd();
  const estimate = estimateCallUsd(prompt, maxOutput);
  if (spent >= cap || spent + estimate > cap) {
    return mock(`Budget cap $${cap.toFixed(2)} reached (spent $${spent.toFixed(4)}).`);
  }
  const base = (process.env.XAI_BASE_URL?.trim() || DEFAULT_BASE).replace(/\/$/, "");
  const model = process.env.XAI_MODEL?.trim() || DEFAULT_MODEL;
  const timeoutMs = options.timeoutMs ?? 20_000;
  try {
    const response = await fetch(`${base}/responses`, {
      method: "POST",
      headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
      body: JSON.stringify({ model, input: prompt, max_output_tokens: maxOutput }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      warnXai(response.status, await xaiErrorMessage(response), key);
      return mock();
    }
    const body = (await response.json()) as {
      output_text?: string;
      output?: Array<{ content?: Array<{ text?: string }> }>;
      usage?: {
        input_tokens?: number;
        output_tokens?: number;
        prompt_tokens?: number;
        completion_tokens?: number;
        cached_tokens?: number;
        input_tokens_details?: { cached_tokens?: number };
      };
    };
    const usage = body.usage ?? {};
    const inputTokens = usage.input_tokens ?? usage.prompt_tokens ?? 0;
    const outputTokens = usage.output_tokens ?? usage.completion_tokens ?? 0;
    const cached = usage.cached_tokens ?? usage.input_tokens_details?.cached_tokens ?? 0;
    const rate = prices();
    const uncached = Math.max(0, inputTokens - cached);
    const cost = (uncached * rate.input + cached * rate.cached + outputTokens * rate.output) / 1_000_000;
    if (cost > 0) await addSpent(cost);
    const nested = body.output
      ?.flatMap((item) => item.content ?? [])
      .map((part) => part.text ?? "")
      .join("")
      .trim();
    const text = (body.output_text ?? nested ?? "").trim();
    if (!text) {
      warnXai(response.status, "xAI responses returned no text", key);
      return mock();
    }
    return { text, mode: "live" };
  } catch (error) {
    const timedOut = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
    const message = error instanceof Error ? error.message : "xAI request failed";
    warnXai(timedOut ? 408 : 0, message, key);
    return mock();
  }
}
