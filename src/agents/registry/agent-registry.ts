import type { Agent } from "@/agents/core/types";
import { AppError } from "@/lib/utils/errors";

export class AgentRegistry {
  private readonly agents = new Map<string, Agent>();

  register(agent: Agent): void {
    this.agents.set(agent.id, agent);
  }

  get(agentId: string): Agent {
    const agent = this.agents.get(agentId);
    if (!agent) {
      throw new AppError("AGENT_NOT_FOUND", `Agent ${agentId} not found`, 404);
    }
    return agent;
  }

  list(): Agent[] {
    return [...this.agents.values()];
  }

  has(agentId: string): boolean {
    return this.agents.has(agentId);
  }

  clear(): void {
    this.agents.clear();
  }
}

export const agentRegistry = new AgentRegistry();
