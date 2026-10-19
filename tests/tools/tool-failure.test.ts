import { afterEach, describe, expect, it } from "vitest";
import { executeMockWorkflow } from "@/agents/orchestrator/task-orchestrator";
import { agentRegistry } from "@/agents/registry/agent-registry";
import { registerDefaultAgents } from "@/agents/registry/bootstrap";
import { AppError } from "@/lib/utils/errors";
import type { TaskRecord } from "@/types/domain";
import { registerDefaultTools } from "@/tools/adapters";
import { LocalEchoTool } from "@/tools/adapters/local-echo-tool";
import { toolRegistry } from "@/tools/core/tool-registry";
import type { Tool } from "@/tools/core/types";
import { MockWorkflowEngine } from "@/workflows/core/mock-workflow-engine";

function restoreTools(): void {
  toolRegistry.register(new LocalEchoTool());
  agentRegistry.clear();
  registerDefaultAgents();
}

function failingTool(execute: Tool["execute"]): Tool {
  return {
    id: "local.echo",
    name: "Failing Echo",
    description: "Stand-in that fails a mock tool call.",
    requiresApproval: false,
    execute,
  };
}

const task: TaskRecord = {
  id: "task_tool_failure",
  workflowId: "workflow_tool_failure",
  input: {
    title: "Tool failure",
    description: "Exercise a failing local tool",
    requestedBy: "qa",
  },
  status: "queued",
  createdAt: "2026-10-19T00:00:00.000Z",
  updatedAt: "2026-10-19T00:00:00.000Z",
};

describe("tool execution failure", () => {
  afterEach(() => {
    restoreTools();
  });

  it("reports an unknown tool with the shared not-found error", () => {
    let caught: unknown;
    try {
      toolRegistry.get("tool.missing");
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(AppError);
    if (!(caught instanceof AppError)) {
      return;
    }
    expect(caught.code).toBe("TOOL_NOT_FOUND");
    expect(caught.status).toBe(404);
    expect(caught.message).toContain("tool.missing");
  });

  it("fails the mock workflow when the tool reports an unsuccessful result", async () => {
    registerDefaultTools();
    registerDefaultAgents();
    toolRegistry.register(
      failingTool(async () => ({
        ok: false,
        output: "echo unavailable",
      })),
    );

    const result = await executeMockWorkflow(task.id, task.input.description);

    expect(result.status).toBe("failed");
    expect(result.currentStep).toBe("error");
    expect(result.result).toBe("echo unavailable");
    expect(
      result.timeline.some((message) =>
        message.content.includes("echo unavailable"),
      ),
    ).toBe(true);
  });

  it("retries a throwing tool and then surfaces the error", async () => {
    registerDefaultTools();
    registerDefaultAgents();
    let attempts = 0;
    toolRegistry.register(
      failingTool(async () => {
        attempts += 1;
        throw new Error("echo exploded");
      }),
    );

    const engine = new MockWorkflowEngine();
    await expect(engine.start(task)).rejects.toThrow("echo exploded");
    expect(attempts).toBe(2);
  });
});
