import { afterEach, expect, it, vi } from "vitest";
import { resolveEventMode } from "../src/config.js";
import { hubQueueSize, postHub, resetHubQueueForTests } from "../src/http.js";
import { installProcessGuards } from "../src/server.js";

afterEach(() => {
  resetHubQueueForTests();
  vi.restoreAllMocks();
});

it("does not call an event live unless an xAI key is set", () => {
  expect(resolveEventMode({ TOOLS_MODE: "mock", XAI_API_KEY: "xai-test" })).toBe("mock");
  expect(resolveEventMode({ XAI_API_KEY: "" })).toBe("mock");
  expect(resolveEventMode({})).toBe("mock");
  expect(resolveEventMode({ XAI_API_KEY: "xai-test" })).toBe("live");
});

it("queues a hub POST instead of throwing when the hub is down", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("ECONNREFUSED"));
  const response = await postHub("http://127.0.0.1:9/api/events", { dept: "sales", task_id: "t1" });
  expect(response).toBeNull();
  expect(hubQueueSize()).toBe(1);
});

it("logs an unhandled rejection instead of leaving it uncaught", async () => {
  installProcessGuards();
  const seen: unknown[] = [];
  const previous = process.listeners("unhandledRejection");
  process.removeAllListeners("unhandledRejection");
  installProcessGuardsReset: {
    // installProcessGuards is once-only; invoke the listener it already attached.
  }
  process.on("unhandledRejection", (reason) => seen.push(reason));
  for (const listener of previous) process.on("unhandledRejection", listener);
  const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const rejection = Promise.reject(new Error("fetch failed"));
  await new Promise((resolve) => setImmediate(resolve));
  process.emit("unhandledRejection", new Error("fetch failed"), rejection);
  expect(logged.mock.calls.some((call) => String(call[0]).includes("unhandledRejection"))).toBe(true);
  await rejection.catch(() => undefined);
});
