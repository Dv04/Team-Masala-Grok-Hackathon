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

export const HUB_QUEUE_LIMIT = 40;

type HubJob = { url: string; body: string; attempts: number };

const hubQueue: HubJob[] = [];
let flushing = false;
let flushTimer: ReturnType<typeof setTimeout> | undefined;

export function hubQueueSize(): number {
  return hubQueue.length;
}

export function resetHubQueueForTests(): void {
  hubQueue.splice(0);
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = undefined;
}

/** POST to the departments hub. Retries with backoff, then keeps a bounded queue instead of throwing. */
export async function postHub(url: string | URL, body: unknown, options: { timeoutMs?: number; retries?: number } = {}): Promise<Response | null> {
  const href = String(url);
  const payload = JSON.stringify(body);
  try {
    const response = await requestJson(
      href,
      { method: "POST", headers: { "content-type": "application/json" }, body: payload },
      { timeoutMs: options.timeoutMs ?? 8000, retries: options.retries ?? 3 },
    );
    if (response.status >= 500) {
      rememberHubPost(href, payload);
      return response;
    }
    void flushHubQueue();
    return response;
  } catch (error) {
    console.error(`hub POST failed; queued (${href})`, error instanceof Error ? error.message : error);
    rememberHubPost(href, payload);
    return null;
  }
}

function rememberHubPost(url: string, body: string): void {
  if (hubQueue.length >= HUB_QUEUE_LIMIT) hubQueue.shift();
  hubQueue.push({ url, body, attempts: 0 });
  scheduleFlush(200);
}

function scheduleFlush(ms: number): void {
  if (flushTimer) return;
  flushTimer = setTimeout(() => {
    flushTimer = undefined;
    void flushHubQueue();
  }, ms);
  flushTimer.unref?.();
}

export async function flushHubQueue(): Promise<void> {
  if (flushing) return;
  flushing = true;
  try {
    while (hubQueue.length) {
      const job = hubQueue[0];
      if (!job) break;
      try {
        const response = await requestJson(
          job.url,
          { method: "POST", headers: { "content-type": "application/json" }, body: job.body },
          { timeoutMs: 4000, retries: 1 },
        );
        if (response.status >= 500) throw new Error(`hub returned ${response.status}`);
        hubQueue.shift();
      } catch (error) {
        job.attempts += 1;
        console.error(`hub flush waiting (${job.url})`, error instanceof Error ? error.message : error);
        scheduleFlush(Math.min(5000, 100 * 2 ** Math.min(job.attempts, 6)));
        break;
      }
    }
  } finally {
    flushing = false;
  }
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
