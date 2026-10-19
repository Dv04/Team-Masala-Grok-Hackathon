export type TaskStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "succeeded"
  | "failed";

export type WorkflowStatus = "pending" | "running" | "succeeded" | "failed";

export type AgentRole = string;

export interface AgentMessage {
  id: string;
  role: "system" | "agent" | "tool" | "human";
  agentRole?: AgentRole;
  content: string;
  createdAt: string;
}

export interface TaskInput {
  title: string;
  description: string;
  requestedBy: string;
  roleHints?: AgentRole[];
}

export interface TaskRecord {
  id: string;
  input: TaskInput;
  status: TaskStatus;
  workflowId: string;
  result?: string;
  error?: string;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowRecord {
  id: string;
  taskId: string;
  name: string;
  status: WorkflowStatus;
  currentStep: string;
  steps: string[];
  timeline: AgentMessage[];
  updatedAt: string;
}

export interface ApiErrorShape {
  code: string;
  message: string;
  details?: unknown;
}
