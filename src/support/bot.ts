import { runCustomerGate } from "../contract/gate.js";
import { grokText } from "../grok.js";
import { newId } from "../ids.js";
import { planIssue } from "../engineering/bot.js";
import { draftOutreach } from "../sales/bot.js";
import type { ServiceCtx } from "../service/types.js";
import { createSupportAdapters, classify, INBOX, type InboxMessage, type SupportAdapters } from "./adapters.js";
import { loadFaq, saveFaq, searchFaq } from "./knowledge.js";

let adapters: SupportAdapters = createSupportAdapters();

export function useSupportAdapters(next: SupportAdapters): void {
  adapters = next;
}

export async function triage(ctx: ServiceCtx): Promise<Record<string, unknown>> {
  const client = ctx.clientFor("support");
  const taskId = newId("triage");
  await client.log({ task_id: taskId, status: "queued", summary: "Queued inbox triage", output: { tool: "chatwoot" } });
  await client.log({ task_id: taskId, status: "running", summary: "Reading the sample inbox", output: { tool: "inbox-zero" } });
  const messages = await adapters.listInbox();
  const items = messages.map((message) => ({
    id: message.id,
    from_name: message.from_name,
    intent: classify(message.body),
    channel: message.channel,
  }));
  await client.log({
    task_id: taskId,
    status: "done",
    summary: `Triaged ${items.length} messages`,
    output: { count: items.length, intents: items.map((item) => item.intent) },
  });
  return { task_id: taskId, messages: items };
}

export async function updateMacro(
  ctx: ServiceCtx,
  input: { parentId: string; question: string; answer: string },
): Promise<{ task_id: string; faq_id: string }> {
  const entries = await loadFaq(ctx.dataDir);
  const faqId = newId("faq");
  entries.push({ id: faqId, q: input.question, a: input.answer, tags: ["macro"], published: true });
  await saveFaq(ctx.dataDir, entries);
  const taskId = newId("macro");
  await ctx.clientFor("support").log({
    task_id: taskId,
    parent_id: input.parentId,
    status: "done",
    summary: "Updated a support macro after engineering shipped a fix",
    output: { kind: "macro_update", faq_id: faqId },
  });
  return { task_id: taskId, faq_id: faqId };
}

export async function draftReply(
  ctx: ServiceCtx,
  input: { message_id?: string; message?: InboxMessage; timeoutMs?: number; parentId?: string },
): Promise<Record<string, unknown>> {
  const client = ctx.clientFor("support");
  const messages = input.message ? [input.message] : await adapters.listInbox();
  const message = messages.find((item) => item.id === input.message_id) ?? messages[0] ?? INBOX[0];
  if (!message) throw new Error("No support message to answer");
  const intent = classify(message.body);
  const taskId = newId("reply");
  const faq = await loadFaq(ctx.dataDir);
  const hits = searchFaq(faq, message.body);
  await adapters.retrieve(message.body, hits);
  await client.log({
    task_id: taskId,
    ...(input.parentId ? { parent_id: input.parentId } : {}),
    status: "queued",
    summary: `Queued a reply for ${message.from_name}`,
    output: { message_id: message.id, intent },
  });
  const first = message.from_name.split(" ")[0] || "there";
  if (intent === "design") {
    const caption = "A one-page setup card for Masala Desk: share the inbox, assign the note, and leave refunds for the founder.";
    const gate = await runCustomerGate({
      client,
      taskId,
      kind: "design_request",
      content: caption,
      summary: "Asking design for a setup diagram",
      deliver: "handoff",
      timeoutMs: input.timeoutMs,
      send: async () => ({ asset: "diagram", message_id: message.id }),
    });
    return { task_id: taskId, intent, handed_off: gate.handed_off, sent: gate.sent };
  }
  if (intent === "churn") {
    const note = await runCustomerGate({
      client,
      taskId,
      ...(input.parentId ? { parentId: input.parentId } : {}),
      kind: "customer_reply",
      content: `Hi ${first}, I flagged this for sales so they can talk through staying on Masala Desk and growing the shared inbox. Nothing is cancelled yet.`,
      summary: "Noted a churn risk and handed it to sales",
      timeoutMs: input.timeoutMs,
      context: { message_id: message.id },
    });
    const follow = await draftOutreach(ctx, {
      parentId: taskId,
      limit: 1,
      skipDesign: true,
      timeoutMs: input.timeoutMs,
      icp: `${message.from_name} may churn and could grow the shared inbox`,
    });
    return { task_id: taskId, intent, sent: note.sent, sales_task_id: follow.task_id, follow };
  }
  if (intent === "refund" || intent === "pricing") {
    const kind = intent === "refund" ? "refund" : "pricing";
    const content =
      kind === "refund"
        ? `Hi ${first}, I can queue a refund review for the damaged order. The refund waits for a founder, and nothing is returned until that decision is in.`
        : `Hi ${first}, I can file this pricing change. The price stays as it is until a founder approves it.`;
    const gate = await runCustomerGate({
      client,
      taskId,
      kind,
      content,
      summary: kind === "refund" ? "Drafted a refund review" : "Drafted a pricing change",
      timeoutMs: input.timeoutMs,
      context: { message_id: message.id },
    });
    return { task_id: taskId, intent, sent: gate.sent, decision: gate.decision ?? null };
  }
  const grok = hits[0] ? null : await grokText(`Answer this buyer in one or two plain sentences: ${message.body}`);
  const answer = hits[0]?.a ?? grok?.text ?? "Thanks for writing in. A teammate will follow up with the details shortly.";
  let faqId: string | undefined;
  if (!hits[0]) {
    faqId = newId("faq");
    faq.push({ id: faqId, q: message.body, a: answer, tags: ["draft"], published: false });
    await saveFaq(ctx.dataDir, faq);
  }
  const content = `Hi ${first}, ${answer}`;
  const gate = await runCustomerGate({
    client,
    taskId,
    ...(input.parentId ? { parentId: input.parentId } : {}),
    kind: "customer_reply",
    content,
    summary: "Drafted a customer reply from the FAQ",
    timeoutMs: input.timeoutMs,
    context: { message_id: message.id },
    send: async () => ({
      message_id: message.id,
      ...(faqId ? { faq_id: faqId } : {}),
      ...(grok ? { grok: grok.mode } : {}),
    }),
  });
  let engineering: Record<string, unknown> | undefined;
  let etaTaskId: string | undefined;
  if (intent === "bug" && gate.sent) {
    engineering = await planIssue(ctx, {
      parentId: taskId,
      issue: {
        number: 107,
        title: "Support bug: timeout while attaching a file",
        body: "The shared inbox times out on file attach. Reproduced from a support ticket.",
        labels: ["bug", "from-support"],
        needs_hire: false,
      },
    });
    etaTaskId = newId("eta");
    await runCustomerGate({
      client,
      taskId: etaTaskId,
      parentId: String(engineering.task_id),
      kind: "customer_reply",
      content: `Hi ${first}, we opened an engineering task for the file timeout. A fix should be ready within two business days, and we will write again when it ships.`,
      summary: "Told the customer the fix ETA",
      timeoutMs: input.timeoutMs,
      context: { message_id: message.id },
    });
  }
  return {
    task_id: taskId,
    intent,
    sent: gate.sent,
    decision: gate.decision ?? null,
    ...(engineering ? { engineering_task_id: engineering.task_id } : {}),
    ...(etaTaskId ? { eta_task_id: etaTaskId } : {}),
  };
}
