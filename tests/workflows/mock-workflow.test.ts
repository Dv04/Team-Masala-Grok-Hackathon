import { describe, expect, it } from "vitest";
import { executeMockWorkflow } from "@/agents/orchestrator/task-orchestrator";
import { registerDefaultAgents } from "@/agents/registry/bootstrap";
import { registerDefaultTools } from "@/tools/adapters";

describe("LOCAL MOCK workflow", () => {
  it("completes successfully", async () => {
    registerDefaultTools();
    registerDefaultAgents();

    const result = await executeMockWorkflow("task_1", "run workflow");

    expect(result.status).toBe("succeeded");
    expect(result.timeline.length).toBeGreaterThan(2);
    expect(result.result).toContain("MOCK");
  });
});
