import type { TaskRecord, WorkflowRecord } from "@/types/domain";

export interface WorkflowEngine {
  start(task: TaskRecord): Promise<WorkflowRecord>;
}
