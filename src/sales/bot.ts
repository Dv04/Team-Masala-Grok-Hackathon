import { runCustomerGate } from "../contract/gate.js";
import { newId } from "../ids.js";
import type { ServiceCtx } from "../service/types.js";
import { recordLeadQuestion } from "../support/knowledge.js";
import { createSalesAdapters, publicLead, type Lead, type SalesAdapters } from "./adapters.js";

let adapters: SalesAdapters = createSalesAdapters();

export function useSalesAdapters(next: SalesAdapters): void {
  adapters = next;
}

export async function findLeads(
  ctx: ServiceCtx,
  input: { icp?: string; limit?: number; parentId?: string },
): Promise<Record<string, unknown>> {
  const client = ctx.clientFor("sales");
  const taskId = newId("lead");
  const icp = input.icp?.trim() || "independent coffee roasters that need a shared inbox";
  const limit = input.limit ?? 3;
  const parent = input.parentId ? { parent_id: input.parentId } : {};
  await client.log({
    task_id: taskId,
    ...parent,
    status: "queued",
    summary: "Queued a lead search",
    output: { icp },
  });
  await client.log({
    task_id: taskId,
    status: "running",
    summary: "Finding leads with OpenOutreach",
    output: { tool: "openoutreach.find" },
  });
  const found = await adapters.openoutreach.find(icp, limit);
  const verified: Lead[] = [];
  for (const lead of found) {
    const check = await adapters.reacher.check(lead.email);
    const next = { ...lead, emailStatus: check.is_reachable === "safe" ? "valid" as const : "invalid" as const };
    verified.push(next);
    await client.log({
      task_id: taskId,
      status: "running",
      summary: `Checked an address for ${lead.company}`,
      output: { lead_id: lead.id, company: lead.company, email_status: next.emailStatus, tool: "reacher" },
    });
  }
  const kept = verified.filter((lead) => lead.emailStatus === "valid");
  await adapters.crm.write(ctx.dataDir, kept);
  for (const lead of kept) {
    await adapters.twenty.upsertPerson(lead);
  }
  await client.log({
    task_id: taskId,
    status: "done",
    summary: `Built a lead list of ${kept.length}`,
    output: { lead_count: kept.length, companies: kept.map((lead) => lead.company), tool: "twenty" },
  });
  const knowledge = [];
  for (const lead of kept) {
    if (!lead.question) continue;
    knowledge.push(
      await recordLeadQuestion(ctx, {
        question: lead.question,
        company: lead.company,
        leadId: lead.id,
        parentId: taskId,
      }),
    );
  }
  return { task_id: taskId, icp, leads: kept.map(publicLead), knowledge };
}

export async function draftOutreach(
  ctx: ServiceCtx,
  input: { icp?: string; limit?: number; timeoutMs?: number; parentId?: string; skipDesign?: boolean },
): Promise<Record<string, unknown>> {
  const client = ctx.clientFor("sales");
  const batchId = newId("outreach");
  const icp = input.icp?.trim() || "independent coffee roasters that need a shared inbox";
  const leads = await adapters.openoutreach.find(icp, input.limit ?? 1);
  await client.log({
    task_id: batchId,
    ...(input.parentId ? { parent_id: input.parentId } : {}),
    status: "queued",
    summary: "Queued first-touch outreach",
    output: { icp, lead_count: leads.length },
  });
  let design: { handed_off: boolean } | null = null;
  let designId: string | null = null;
  if (!input.skipDesign) {
    designId = newId("design");
    const caption =
      "Masala Desk helps a small roasting team share one inbox. Pin this card by the counter so everyone can see who owns the next reply.";
    design = await runCustomerGate({
      client,
      taskId: designId,
      parentId: batchId,
      kind: "design_request",
      content: caption,
      summary: "Asking design for a counter card",
      deliver: "handoff",
      timeoutMs: input.timeoutMs,
      send: async () => ({ asset: "caption" }),
    });
  }
  const emails = [];
  for (const lead of leads) {
    const taskId = newId("email");
    const content = `Hi ${lead.name.split(" ")[0]}, ${lead.company} can share one inbox without adding another tool to the roast day. Masala Desk keeps the first note with a founder until you say it is welcome.`;
    const result = await runCustomerGate({
      client,
      taskId,
      parentId: batchId,
      kind: "outbound_email",
      content,
      context: { first_contact: true, lead_id: lead.id },
      summary: `First email for ${lead.company}`,
      timeoutMs: input.timeoutMs,
      send: async () => adapters.warmbly.enroll(lead),
    });
    emails.push({ task_id: taskId, company: lead.company, sent: result.sent, decision: result.decision ?? null });
  }
  await client.log({
    task_id: batchId,
    ...(input.parentId ? { parent_id: input.parentId } : {}),
    status: "done",
    summary: "Finished the outreach batch",
    output: { design_handed_off: design?.handed_off ?? false, emails: emails.length },
  });
  return { task_id: batchId, design_task_id: designId, design, emails };
}
