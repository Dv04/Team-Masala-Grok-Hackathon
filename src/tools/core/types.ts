export interface ToolExecutionContext {
  taskId: string;
  actor: string;
}

export interface ToolExecutionResult {
  ok: boolean;
  output: string;
  metadata?: Record<string, unknown>;
}

export interface Tool {
  id: string;
  name: string;
  description: string;
  requiresApproval: boolean;
  execute(input: string, context: ToolExecutionContext): Promise<ToolExecutionResult>;
}
