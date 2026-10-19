import { describe, expect, it } from "vitest";
import { registerDefaultAgents } from "@/agents/registry/bootstrap";
import { agentRegistry } from "@/agents/registry/agent-registry";

describe("agent bootstrap", () => {
  it("registers configured default agents", () => {
    agentRegistry.clear();
    registerDefaultAgents();

    expect(agentRegistry.list().length).toBeGreaterThanOrEqual(3);
  });
});
