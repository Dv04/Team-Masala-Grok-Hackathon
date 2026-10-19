import { MockGrokAgent } from "@/agents/providers/mock-grok-agent";
import { XaiGrokAgent } from "@/agents/providers/xai-grok-agent";
import { agentRegistry } from "@/agents/registry/agent-registry";
import { env } from "@/lib/config/env";

const roles = [
  {
    id: "agent.orchestrator",
    role: "orchestrator",
    description: "Coordinates multi-step task execution and handoffs.",
  },
  {
    id: "agent.executor",
    role: "executor",
    description: "Executes implementation steps and tool calls.",
  },
  {
    id: "agent.reviewer",
    role: "reviewer",
    description: "Performs quality and correctness review checks.",
  },
];

export function registerDefaultAgents(): void {
  for (const role of roles) {
    if (agentRegistry.has(role.id)) {
      continue;
    }

    if (env.GROK_PROVIDER_MODE === "xai") {
      agentRegistry.register(
        new XaiGrokAgent(role.id, role.role, role.description),
      );
    } else {
      agentRegistry.register(
        new MockGrokAgent(role.id, role.role, role.description),
      );
    }
  }
}
