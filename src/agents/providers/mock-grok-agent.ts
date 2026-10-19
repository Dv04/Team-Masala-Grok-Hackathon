import type {
  Agent,
  AgentExecutionContext,
  AgentExecutionResult,
} from "@/agents/core/types";
import { createId } from "@/lib/utils/id";
import { nowIso } from "@/lib/utils/time";

export class MockGrokAgent implements Agent {
  constructor(
    public readonly id: string,
    public readonly role: string,
    public readonly description: string,
  ) {}

  provider = "mock" as const;

  async execute(context: AgentExecutionContext): Promise<AgentExecutionResult> {
    const echoTool = context.toolRegistry.get("local.echo");
    const toolResult = await echoTool.execute(context.input, {
      taskId: context.taskId,
      actor: this.role,
    });

    return {
      ok: true,
      output: `MOCK(${this.role}): ${toolResult.output}`,
      usedTools: [echoTool.id],
      message: {
        id: createId("msg"),
        role: "agent",
        agentRole: this.role,
        content: `Completed local mock execution for ${this.role}`,
        createdAt: nowIso(),
      },
    };
  }
}
