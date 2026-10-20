import type { IncomingMessage, ServerResponse } from "node:http";

export class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > 1_000_000) throw new HttpError(413, "Body too large");
    chunks.push(buffer);
  }
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new HttpError(400, "Invalid JSON");
  }
}

export function sendJson(res: ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}): void {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(data),
    "cache-control": "no-store",
    ...headers,
  });
  res.end(data);
}

export const POLL_FALLBACK_MS = 10_000;

export async function requestJson(url: string | URL, init: RequestInit = {}, options: { timeoutMs?: number; retries?: number } = {}): Promise<Response> {
  const timeoutMs = options.timeoutMs ?? 8000;
  const retries = options.retries ?? 0;
  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(url, { ...init, signal: AbortSignal.timeout(timeoutMs) });
      if (response.status >= 500 && attempt < retries) {
        await delay(40 * 2 ** attempt);
        continue;
      }
      return response;
    } catch (error) {
      lastError = error;
      if (attempt >= retries) break;
      await delay(40 * 2 ** attempt);
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Request failed");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const mirrorQueue: { url: string; body: string }[] = [];
let mirrorTimer: ReturnType<typeof setTimeout> | undefined;

export function queueMirror(url: string, body: unknown): void {
  mirrorQueue.push({ url, body: JSON.stringify(body) });
  if (mirrorTimer) return;
  mirrorTimer = setTimeout(() => {
    const batch = mirrorQueue.splice(0);
    mirrorTimer = undefined;
    void Promise.all(
      batch.map((item) =>
        fetch(item.url, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: item.body,
          signal: AbortSignal.timeout(4000),
        }).catch(() => undefined),
      ),
    );
  }, 25);
  mirrorTimer.unref?.();
}

export function sendText(res: ServerResponse, status: number, body: string, contentType: string, headers: Record<string, string> = {}): void {
  res.writeHead(status, {
    "content-type": contentType,
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
    ...headers,
  });
  res.end(body);
}
