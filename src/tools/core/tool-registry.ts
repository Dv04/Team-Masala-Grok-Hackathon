import type { Tool } from "@/tools/core/types";
import { AppError } from "@/lib/utils/errors";

export class ToolRegistry {
  private readonly tools = new Map<string, Tool>();

  register(tool: Tool): void {
    this.tools.set(tool.id, tool);
  }

  get(toolId: string): Tool {
    const tool = this.tools.get(toolId);
    if (!tool) {
      throw new AppError("TOOL_NOT_FOUND", `Tool ${toolId} not found`, 404);
    }
    return tool;
  }

  list(): Tool[] {
    return [...this.tools.values()];
  }
}

export const toolRegistry = new ToolRegistry();
