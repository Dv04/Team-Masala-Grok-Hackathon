import { registerDefaultAgents } from "@/agents/registry/bootstrap";
import { agentRegistry } from "@/agents/registry/agent-registry";

export function listAgents() {
  registerDefaultAgents();
  return agentRegistry.list().map((agent) => ({
    id: agent.id,
    role: agent.role,
    description: agent.description,
    provider: agent.provider,
  }));
}
