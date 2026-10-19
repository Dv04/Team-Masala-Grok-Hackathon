import type { AgentMessage, AgentRole } from "@/types/domain";
import type { ToolRegistry } from "@/tools/core/tool-registry";

export interface AgentExecutionContext {
  taskId: string;
  input: string;
  role: AgentRole;
  messages: AgentMessage[];
  toolRegistry: ToolRegistry;
}

export interface AgentExecutionResult {
  ok: boolean;
  message: AgentMessage;
  usedTools: string[];
  output: string;
  error?: string;
}

export interface Agent {
  id: string;
  role: AgentRole;
  description: string;
  provider: "mock" | "xai";
  execute(context: AgentExecutionContext): Promise<AgentExecutionResult>;
}
