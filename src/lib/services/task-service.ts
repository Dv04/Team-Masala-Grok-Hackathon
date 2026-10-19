import { registerDefaultAgents } from "@/agents/registry/bootstrap";
import { registerDefaultTools } from "@/tools/adapters";
import { createTaskRequestSchema } from "@/lib/schemas/api";
import type { TaskRecord } from "@/types/domain";
import { createId } from "@/lib/utils/id";
import { nowIso } from "@/lib/utils/time";
import { store } from "@/lib/data/in-memory-store";
import { AppError } from "@/lib/utils/errors";
import { MockWorkflowEngine } from "@/workflows/core/mock-workflow-engine";

const workflowEngine = new MockWorkflowEngine();

function ensureBootstrap(): void {
  registerDefaultTools();
  registerDefaultAgents();
}

export function listTasks(): TaskRecord[] {
  ensureBootstrap();
  return store.listTasks();
}

export async function createTask(payload: unknown): Promise<TaskRecord> {
  ensureBootstrap();

  const parsed = createTaskRequestSchema.safeParse(payload);
  if (!parsed.success) {
    throw new AppError("INVALID_TASK_INPUT", "Task input validation failed", 400, {
      issues: parsed.error.issues,
    });
  }

  const timestamp = nowIso();
  const task: TaskRecord = {
    id: createId("task"),
    workflowId: createId("workflow"),
    input: parsed.data,
    status: "queued",
    createdAt: timestamp,
    updatedAt: timestamp,
  };

  store.createTask(task);
  void runTaskWorkflow(task.id);
  return task;
}

async function runTaskWorkflow(taskId: string): Promise<void> {
  const queuedTask = store.listTasks().find((task) => task.id === taskId);
  if (!queuedTask) {
    return;
  }

  store.updateTask(taskId, {
    status: "running",
    updatedAt: nowIso(),
  });

  try {
    const completedWorkflow = await workflowEngine.start(queuedTask);
    store.upsertWorkflow(completedWorkflow);

    store.updateTask(taskId, {
      status: completedWorkflow.status === "succeeded" ? "succeeded" : "failed",
      updatedAt: nowIso(),
      result:
        completedWorkflow.status === "succeeded"
          ? "LOCAL MOCK workflow completed"
          : undefined,
      error:
        completedWorkflow.status === "failed"
          ? "LOCAL MOCK workflow failed"
          : undefined,
    });
  } catch (error) {
    store.updateTask(taskId, {
      status: "failed",
      updatedAt: nowIso(),
      error: error instanceof Error ? error.message : "Unknown workflow error",
    });
  }
}
