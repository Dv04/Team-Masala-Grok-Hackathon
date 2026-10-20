/** Per-tool live call budget. A hung binary or HTTP client must not stall inbound reactions. */
export const TOOL_TIMEOUT_MS = 3_000;

/**
 * Run one live tool call. Missing config, a thrown error, or a timeout returns the mock
 * result labeled `mode: "mock"`. This function does not throw.
 */
export async function withToolFallback<T>(
  configured: boolean,
  live: (signal: AbortSignal) => Promise<T>,
  mock: () => Promise<T> | T,
): Promise<T> {
  try {
    if (!configured) return label(await mock(), "mock");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TOOL_TIMEOUT_MS);
    const pending = Promise.resolve()
      .then(() => live(controller.signal))
      .then((value) => ({ ok: true as const, value }))
      .catch(() => ({ ok: false as const }));
    const timedOut = new Promise<{ ok: false }>((resolve) => {
      const fail = () => resolve({ ok: false });
      if (controller.signal.aborted) fail();
      else controller.signal.addEventListener("abort", fail, { once: true });
    });
    try {
      const outcome = await Promise.race([pending, timedOut]);
      if (outcome.ok) return outcome.value;
      return label(await mock(), "mock");
    } finally {
      clearTimeout(timer);
    }
  } catch {
    try {
      return label(await mock(), "mock");
    } catch {
      return label({} as T, "mock");
    }
  }
}

function label<T>(value: T, mode: "live" | "mock"): T {
  if (Array.isArray(value)) return Object.assign(value, { mode });
  if (value !== null && typeof value === "object") return { ...(value as Record<string, unknown>), mode } as T;
  return value;
}
