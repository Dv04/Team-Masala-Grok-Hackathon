import type { WorkflowEngine } from "@/workflows/core/types";
import type { TaskRecord, WorkflowRecord } from "@/types/domain";
import { executeMockWorkflow } from "@/agents/orchestrator/task-orchestrator";
import { nowIso } from "@/lib/utils/time";
import { withRetry } from "@/lib/utils/retry";

export class MockWorkflowEngine implements WorkflowEngine {
  async start(task: TaskRecord): Promise<WorkflowRecord> {
    const execution = await withRetry(
      () => executeMockWorkflow(task.id, task.input.description),
      {
        retries: 1,
      },
    );

    return {
      id: task.workflowId,
      taskId: task.id,
      name: "LOCAL MOCK Workflow",
      status: execution.status,
      currentStep: execution.currentStep,
      steps: ["orchestrate", "execute", "review"],
      timeline: execution.timeline,
      updatedAt: nowIso(),
    };
  }
}
