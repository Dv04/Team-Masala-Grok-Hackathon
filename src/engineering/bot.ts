import { runCustomerGate } from "../contract/gate.js";
import { newId } from "../ids.js";
import type { ServiceCtx } from "../service/types.js";
import { createEngineeringAdapters, wantsHire, type EngineeringAdapters, type Issue } from "./adapters.js";

let adapters: EngineeringAdapters = createEngineeringAdapters();

export function useEngineeringAdapters(next: EngineeringAdapters): void {
  adapters = next;
}

export async function planIssue(
  ctx: ServiceCtx,
  input: { issue?: Issue; parentId?: string } = {},
): Promise<Record<string, unknown>> {
  const client = ctx.clientFor("engineering");
  const taskId = newId("plan");
  const loaded = await adapters.getIssue(input.issue);
  const issue = loaded.issue;
  await client.log({
    task_id: taskId,
    ...(input.parentId ? { parent_id: input.parentId } : {}),
    status: "queued",
    summary: `Queued a plan for issue #${issue.number}`,
    output: { issue_number: issue.number, title: issue.title },
  });
  await client.log({
    task_id: taskId,
    ...(input.parentId ? { parent_id: input.parentId } : {}),
    status: "running",
    summary: `Drafting a task plan for issue #${issue.number}`,
    output: { tool: "openhands", mode: loaded.mode },
  });
  const conversation = await adapters.startConversation(issue);
  const steps = [
    `Reproduce issue #${issue.number}: ${issue.title}.`,
    "Write a failing test that shows the timeout.",
    "Patch the smallest module that owns the queue.",
    "Run the suite and attach the result to the issue.",
  ];
  const planText = steps.join(" ");
  const gate = await runCustomerGate({
    client,
    taskId,
    ...(input.parentId ? { parentId: input.parentId } : {}),
    kind: "internal",
    content: planText,
    summary: "Checking the task plan",
    deliver: "handoff",
    send: async () => ({ conversation_id: conversation.conversation_id, steps, issue_number: issue.number }),
  });
  let hireTask: string | undefined;
  if (wantsHire(issue)) {
    hireTask = newId("hire");
    await client.log({
      task_id: hireTask,
      parent_id: taskId,
      status: "done",
      summary: "Hiring signal: backend engineer for the queue worker",
      output: {
        kind: "hire_needed",
        role: "backend engineer",
        reason: `Issue #${issue.number} needs an owner for the queue worker`,
        needs_qa: false,
      },
    });
  }
  return {
    task_id: taskId,
    parent_id: input.parentId ?? null,
    issue_number: issue.number,
    title: issue.title,
    steps,
    conversation_id: conversation.conversation_id,
    mode: conversation.mode,
    handed_off: gate.handed_off,
    ...(hireTask ? { hire_task_id: hireTask, hire_needed: true } : { hire_needed: false }),
  };
}
