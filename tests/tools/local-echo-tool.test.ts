import { describe, expect, it } from "vitest";
import { LocalEchoTool } from "@/tools/adapters/local-echo-tool";

describe("LocalEchoTool", () => {
  it("executes safely in local mode", async () => {
    const tool = new LocalEchoTool();
    const result = await tool.execute("hello", { taskId: "task_1", actor: "tester" });

    expect(result.ok).toBe(true);
    expect(result.output).toContain("hello");
    expect(result.metadata?.mode).toBe("local");
  });
});
