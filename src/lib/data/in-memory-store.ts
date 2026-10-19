import type { TaskRecord, WorkflowRecord } from "@/types/domain";

class InMemoryStore {
  tasks: TaskRecord[] = [];
  workflows: WorkflowRecord[] = [];

  createTask(task: TaskRecord): void {
    this.tasks.unshift(task);
  }

  updateTask(taskId: string, update: Partial<TaskRecord>): TaskRecord | undefined {
    const index = this.tasks.findIndex((task) => task.id === taskId);
    if (index === -1) {
      return undefined;
    }

    this.tasks[index] = {
      ...this.tasks[index],
      ...update,
    };

    return this.tasks[index];
  }

  listTasks(): TaskRecord[] {
    return this.tasks;
  }

  upsertWorkflow(workflow: WorkflowRecord): void {
    const index = this.workflows.findIndex((item) => item.id === workflow.id);
    if (index === -1) {
      this.workflows.unshift(workflow);
      return;
    }

    this.workflows[index] = workflow;
  }

  listWorkflows(): WorkflowRecord[] {
    return this.workflows;
  }

  reset(): void {
    this.tasks = [];
    this.workflows = [];
  }
}

export const store = new InMemoryStore();
