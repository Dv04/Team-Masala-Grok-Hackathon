import { agentRegistry } from "@/agents/registry/agent-registry";
import type { AgentMessage, WorkflowRecord } from "@/types/domain";
import { toolRegistry } from "@/tools/core/tool-registry";
import { createId } from "@/lib/utils/id";
import { nowIso } from "@/lib/utils/time";

export async function executeMockWorkflow(
  taskId: string,
  input: string,
): Promise<Pick<WorkflowRecord, "timeline" | "status" | "currentStep"> & {
  result: string;
}> {
  const orchestrator = agentRegistry.get("agent.orchestrator");
  const executor = agentRegistry.get("agent.executor");
  const reviewer = agentRegistry.get("agent.reviewer");

  const seedMessage: AgentMessage = {
    id: createId("msg"),
    role: "system",
    content: "LOCAL MOCK workflow started",
    createdAt: nowIso(),
  };

  const messages: AgentMessage[] = [seedMessage];

  const orchestratorResult = await orchestrator.execute({
    taskId,
    input,
    role: "orchestrator",
    messages,
    toolRegistry,
  });
  messages.push(orchestratorResult.message);

  const executorResult = await executor.execute({
    taskId,
    input,
    role: "executor",
    messages,
    toolRegistry,
  });
  messages.push(executorResult.message);

  const reviewerResult = await reviewer.execute({
    taskId,
    input,
    role: "reviewer",
    messages,
    toolRegistry,
  });
  messages.push(reviewerResult.message);

  return {
    timeline: messages,
    status: reviewerResult.ok ? "succeeded" : "failed",
    currentStep: reviewerResult.ok ? "complete" : "error",
    result: reviewerResult.ok
      ? `${orchestratorResult.output}
${executorResult.output}
${reviewerResult.output}`
      : reviewerResult.error ?? "Workflow failed",
  };
}
