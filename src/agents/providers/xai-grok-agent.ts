import type {
  Agent,
  AgentExecutionContext,
  AgentExecutionResult,
} from "@/agents/core/types";
import { createId } from "@/lib/utils/id";
import { nowIso } from "@/lib/utils/time";

export class XaiGrokAgent implements Agent {
  provider = "xai" as const;

  constructor(
    public readonly id: string,
    public readonly role: string,
    public readonly description: string,
  ) {}

  async execute(context: AgentExecutionContext): Promise<AgentExecutionResult> {
    return {
      ok: false,
      output: "",
      usedTools: [],
      error:
        "xAI provider adapter contract is ready, but real API invocation is intentionally not enabled in starter mode.",
      message: {
        id: createId("msg"),
        role: "agent",
        agentRole: this.role,
        content: `Provider xAI not configured for task ${context.taskId}`,
        createdAt: nowIso(),
      },
    };
  }
}
