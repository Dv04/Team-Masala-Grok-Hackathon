export const localMockWorkflowDefinition = {
  id: "workflow.local-mock",
  name: "LOCAL MOCK Workflow",
  steps: ["orchestrate", "execute", "review"],
  description:
    "Deterministic local workflow that validates task lifecycles without external APIs.",
};
