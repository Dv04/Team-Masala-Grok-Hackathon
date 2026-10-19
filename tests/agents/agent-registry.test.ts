import { describe, expect, it } from "vitest";
import { AgentRegistry } from "@/agents/registry/agent-registry";
import { MockGrokAgent } from "@/agents/providers/mock-grok-agent";
import { AppError } from "@/lib/utils/errors";

describe("AgentRegistry", () => {
  it("registers and returns agents", () => {
    const registry = new AgentRegistry();
    const agent = new MockGrokAgent("agent.test", "tester", "test agent");

    registry.register(agent);

    expect(registry.get("agent.test")).toBe(agent);
    expect(registry.list()).toHaveLength(1);
  });

  it("keeps a single entry when the same id is registered again", () => {
    const registry = new AgentRegistry();
    const first = new MockGrokAgent(
      "agent.test",
      "tester",
      "first registration",
    );
    const second = new MockGrokAgent(
      "agent.test",
      "reviewer",
      "replacement registration",
    );

    registry.register(first);
    registry.register(second);

    expect(registry.list()).toHaveLength(1);
    expect(registry.has("agent.test")).toBe(true);
    expect(registry.get("agent.test")).toBe(second);
    expect(registry.get("agent.test").description).toBe(
      "replacement registration",
    );
  });

  it("throws a not-found error when looking up an unknown agent", () => {
    const registry = new AgentRegistry();
    registry.register(new MockGrokAgent("agent.test", "tester", "test agent"));

    let caught: unknown;
    try {
      registry.get("agent.missing");
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(AppError);
    if (!(caught instanceof AppError)) {
      return;
    }
    expect(caught.code).toBe("AGENT_NOT_FOUND");
    expect(caught.status).toBe(404);
    expect(caught.message).toContain("agent.missing");
    expect(registry.list()).toHaveLength(1);
  });
});
