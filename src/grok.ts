/** Canned Grok reply. Shown until an xAI key is set; the same function then calls the live API. */
export const GROK_MOCK_TEXT =
  "MOCK Grok: Pulse Studio is a one-page product site for a small team. It explains the product and points buyers to support. No model wrote this sentence.";

const DEFAULT_BASE_URL = "https://api.x.ai/v1";
const DEFAULT_MAX_OUTPUT_TOKENS = 200;
/** xAI reports spend as USD * 1e10. */
const USD_TICKS = 10_000_000_000;

let spentUsd = 0;

export interface GrokTextOptions {
  system?: string;
  timeoutMs?: number;
  maxOutputTokens?: number;
}

/** Live when the key starts with xai-, or when XAI_BASE_URL is set alongside any key. */
export function configuredCopyMode(env: NodeJS.ProcessEnv = process.env): "live" | "mock" {
  const key = env.XAI_API_KEY?.trim() ?? "";
  if (!key) return "mock";
  if (key.startsWith("xai-")) return "live";
  if (env.XAI_BASE_URL?.trim()) return "live";
  return "mock";
}

export function resetGrokBudget(): void {
  spentUsd = 0;
}

export async function grokText(
  prompt: string,
  options: GrokTextOptions = {},
): Promise<{ text: string; mode: "live" | "mock" }> {
  const key = process.env.XAI_API_KEY?.trim() ?? "";
  if (configuredCopyMode() !== "live" || !key) return { text: GROK_MOCK_TEXT, mode: "mock" };
  const remaining = budgetRemaining();
  if (remaining !== undefined && remaining <= 0) {
    warnXai(402, "budget exhausted", key);
    return { text: GROK_MOCK_TEXT, mode: "mock" };
  }
  const maxOutputTokens = options.maxOutputTokens ?? DEFAULT_MAX_OUTPUT_TOKENS;
  const base = (process.env.XAI_BASE_URL?.trim() || DEFAULT_BASE_URL).replace(/\/$/, "");
  const input = options.system
    ? [
        { role: "system", content: options.system },
        { role: "user", content: prompt },
      ]
    : prompt;
  try {
    const response = await fetch(`${base}/responses`, {
      method: "POST",
      headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
      body: JSON.stringify({
        model: process.env.XAI_MODEL?.trim() || "grok-4",
        input,
        max_output_tokens: maxOutputTokens,
      }),
      signal: AbortSignal.timeout(options.timeoutMs ?? 20000),
    });
    if (!response.ok) {
      warnXai(response.status, await errorMessage(response), key);
      return { text: GROK_MOCK_TEXT, mode: "mock" };
    }
    const body = (await response.json()) as {
      output_text?: string;
      output?: Array<{ content?: Array<{ text?: string }> }>;
      usage?: { cost_in_usd_ticks?: number; input_tokens?: number; output_tokens?: number };
    };
    noteSpend(body.usage, maxOutputTokens);
    const nested = body.output
      ?.flatMap((item) => item.content ?? [])
      .map((part) => part.text ?? "")
      .join("")
      .trim();
    const text = (body.output_text ?? nested ?? "").trim();
    if (!text) {
      warnXai(response.status, "xAI responses returned no text", key);
      return { text: GROK_MOCK_TEXT, mode: "mock" };
    }
    return { text, mode: "live" };
  } catch (error) {
    const message = error instanceof Error ? error.message : "xAI request failed";
    warnXai(0, message, key);
    return { text: GROK_MOCK_TEXT, mode: "mock" };
  }
}

function budgetRemaining(): number | undefined {
  const raw = process.env.XAI_BUDGET_USD?.trim();
  if (!raw) return undefined;
  const budget = Number(raw);
  if (!Number.isFinite(budget)) return undefined;
  return budget - spentUsd;
}

function noteSpend(
  usage: { cost_in_usd_ticks?: number; input_tokens?: number; output_tokens?: number } | undefined,
  maxOutputTokens: number,
): void {
  if (usage && typeof usage.cost_in_usd_ticks === "number" && Number.isFinite(usage.cost_in_usd_ticks)) {
    spentUsd += usage.cost_in_usd_ticks / USD_TICKS;
    return;
  }
  const input = usage?.input_tokens ?? 400;
  const output = usage?.output_tokens ?? maxOutputTokens;
  spentUsd += (input * 3 + output * 15) / 1_000_000;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } | string; message?: string };
    if (typeof body.error === "string") return body.error;
    if (body.error && typeof body.error.message === "string") return body.error.message;
    if (typeof body.message === "string") return body.message;
  } catch {
    // Body was not JSON. Fall through to the status text.
  }
  return response.statusText || "request failed";
}

function warnXai(status: number, message: string, key: string): void {
  const cleaned = message
    .replaceAll(key, "[redacted]")
    .replace(/xai-[A-Za-z0-9_-]+/g, "[redacted]")
    .replace(/bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 200);
  console.warn(`xAI error ${status}: ${cleaned || "request failed"}`);
}
