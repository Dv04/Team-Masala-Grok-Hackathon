import { afterEach, describe, expect, it } from "vitest";
import type {
  AgentExecutionContext,
  AgentExecutionResult,
} from "@/agents/core/types";
import { MockGrokAgent } from "@/agents/providers/mock-grok-agent";
import { agentRegistry } from "@/agents/registry/agent-registry";
import { registerDefaultAgents } from "@/agents/registry/bootstrap";
import { store } from "@/lib/data/in-memory-store";
import { createTask } from "@/lib/services/task-service";
import { nowIso } from "@/lib/utils/time";
import { registerDefaultTools } from "@/tools/adapters";
import { LocalEchoTool } from "@/tools/adapters/local-echo-tool";
import { toolRegistry } from "@/tools/core/tool-registry";

const validInput = {
  title: "Lifecycle task",
  description: "Walk the local mock workflow",
  requestedBy: "qa",
};

function restoreRuntime(): void {
  store.reset();
  agentRegistry.clear();
  toolRegistry.register(new LocalEchoTool());
  registerDefaultAgents();
}

async function waitForStatus(taskId: string, status: string): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < 1000) {
    const task = store.listTasks().find((item) => item.id === taskId);
    if (task?.status === status) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  const task = store.listTasks().find((item) => item.id === taskId);
  throw new Error(
    `timed out waiting for ${status}, last status was ${task?.status}`,
  );
}

class DelayedExecutor extends MockGrokAgent {
  async execute(context: AgentExecutionContext): Promise<AgentExecutionResult> {
    await new Promise((resolve) => setTimeout(resolve, 40));
    return super.execute(context);
  }
}

class FailingReviewer extends MockGrokAgent {
  async execute(
    context: AgentExecutionContext,
  ): Promise<AgentExecutionResult> {
    return {
      ok: false,
      output: "",
      usedTools: [],
      error: "review rejected the mock output",
      message: {
        id: "msg_review_fail",
        role: "agent",
        agentRole: this.role,
        content: `Review rejected the mock output for ${context.taskId}`,
        createdAt: nowIso(),
      },
    };
  }
}

describe("mock workflow task lifecycle", () => {
  afterEach(() => {
    restoreRuntime();
  });

  it("moves a task from queued through running to succeeded", async () => {
    store.reset();
    agentRegistry.clear();
    registerDefaultTools();
    agentRegistry.register(
      new MockGrokAgent("agent.orchestrator", "orchestrator", "coordinates"),
    );
    agentRegistry.register(
      new DelayedExecutor("agent.executor", "executor", "executes"),
    );
    agentRegistry.register(
      new MockGrokAgent("agent.reviewer", "reviewer", "reviews"),
    );

    const created = await createTask(validInput);
    expect(created.status).toBe("queued");

    await waitForStatus(created.id, "running");
    await waitForStatus(created.id, "succeeded");

    const stored = store.listTasks().find((task) => task.id === created.id);
    expect(stored?.result).toBe("LOCAL MOCK workflow completed");
    expect(stored?.error).toBeUndefined();

    const workflow = store
      .listWorkflows()
      .find((item) => item.id === created.workflowId);
    expect(workflow).toMatchObject({
      taskId: created.id,
      name: "LOCAL MOCK Workflow",
      status: "succeeded",
      currentStep: "complete",
      steps: ["orchestrate", "execute", "review"],
    });
    expect(
      workflow?.timeline.map((message) => message.agentRole ?? message.role),
    ).toEqual(["system", "orchestrator", "executor", "reviewer"]);
  });

  it("records a failed workflow when review rejects the run", async () => {
    store.reset();
    agentRegistry.clear();
    registerDefaultTools();
    agentRegistry.register(
      new MockGrokAgent("agent.orchestrator", "orchestrator", "coordinates"),
    );
    agentRegistry.register(
      new MockGrokAgent("agent.executor", "executor", "executes"),
    );
    agentRegistry.register(
      new FailingReviewer("agent.reviewer", "reviewer", "reviews"),
    );

    const created = await createTask(validInput);
    await waitForStatus(created.id, "failed");

    const stored = store.listTasks().find((task) => task.id === created.id);
    expect(stored?.error).toBe("LOCAL MOCK workflow failed");
    expect(stored?.result).toBeUndefined();

    const workflow = store
      .listWorkflows()
      .find((item) => item.id === created.workflowId);
    expect(workflow?.status).toBe("failed");
    expect(workflow?.currentStep).toBe("error");
    expect(workflow?.timeline.at(-1)?.content).toBe(
      `Review rejected the mock output for ${created.id}`,
    );
  });
});
