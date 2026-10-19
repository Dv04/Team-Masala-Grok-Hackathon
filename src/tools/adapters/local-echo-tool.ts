import type { Tool, ToolExecutionContext, ToolExecutionResult } from "@/tools/core/types";

export class LocalEchoTool implements Tool {
  id = "local.echo";
  name = "Local Echo Tool";
  description = "Safe local tool for validating tool calls during mock workflow runs.";
  requiresApproval = false;

  async execute(
    input: string,
    context: ToolExecutionContext,
  ): Promise<ToolExecutionResult> {
    return {
      ok: true,
      output: `[echo:${context.taskId}] ${input.trim()}`,
      metadata: {
        actor: context.actor,
        mode: "local",
      },
    };
  }
}
