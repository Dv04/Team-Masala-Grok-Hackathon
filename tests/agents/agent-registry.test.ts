import { describe, expect, it } from "vitest";
import { AgentRegistry } from "@/agents/registry/agent-registry";
import { MockGrokAgent } from "@/agents/providers/mock-grok-agent";

describe("AgentRegistry", () => {
  it("registers and returns agents", () => {
    const registry = new AgentRegistry();
    const agent = new MockGrokAgent("agent.test", "tester", "test agent");

    registry.register(agent);

    expect(registry.get("agent.test")).toBe(agent);
    expect(registry.list()).toHaveLength(1);
  });
});
