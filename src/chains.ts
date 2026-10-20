import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { runCustomerGate } from "./contract/gate.js";
import { grokText } from "./grok.js";
import { newId } from "./ids.js";
import { listingFromUpstream } from "./listing.js";
import { planIssue } from "./engineering/bot.js";
import { draftOutreach, findLeads } from "./sales/bot.js";
import type { ServiceCtx } from "./service/types.js";
import { draftReply, updateMacro } from "./support/bot.js";

export async function chainBug(ctx: ServiceCtx, input: { parentId?: string; timeoutMs?: number } = {}) {
  const reply = await draftReply(ctx, { message_id: "msg_bug", timeoutMs: input.timeoutMs, parentId: input.parentId });
  return { chain: "bug", ...reply };
}

export async function chainLead(ctx: ServiceCtx, input: { parentId?: string; timeoutMs?: number; icp?: string } = {}) {
  const found = await findLeads(ctx, {
    icp: input.icp ?? "independent coffee roasters in Austin",
    limit: 1,
    parentId: input.parentId,
  });
  const knowledge = (found.knowledge as { task_id?: string }[] | undefined)?.[0];
  if (!knowledge?.task_id) throw new Error("The lead chain needs a product question on the first lead");
  const outreach = await draftOutreach(ctx, {
    parentId: knowledge.task_id,
    limit: 1,
    skipDesign: true,
    timeoutMs: input.timeoutMs,
    icp: String(found.icp ?? input.icp ?? ""),
  });
  return {
    chain: "lead_question",
    root_task_id: found.task_id,
    knowledge_task_id: knowledge.task_id,
    outreach_task_id: outreach.task_id,
    outreach,
  };
}

export async function chainChurn(ctx: ServiceCtx, input: { parentId?: string; timeoutMs?: number } = {}) {
  const reply = await draftReply(ctx, { message_id: "msg_churn", timeoutMs: input.timeoutMs, parentId: input.parentId });
  return { chain: "churn", ...reply };
}

export async function chainShipped(ctx: ServiceCtx, input: { parentId?: string; timeoutMs?: number } = {}) {
  const plan = await planIssue(ctx, {
    parentId: input.parentId,
    issue: {
      number: 77,
      title: "File attach timeout fix",
      body: "The shared inbox now accepts attachments without timing out.",
      labels: ["shipped"],
      needs_hire: false,
    },
  });
  const shipId = newId("shipped");
  await ctx.clientFor("engineering").log({
    task_id: shipId,
    parent_id: String(plan.task_id),
    status: "done",
    summary: "Feature shipped: file attach timeout fix",
    output: { kind: "feature_shipped", issue_number: 77 },
  });
  const [outreach, macro] = await Promise.all([
    draftOutreach(ctx, {
      parentId: shipId,
      limit: 1,
      skipDesign: true,
      timeoutMs: input.timeoutMs,
      icp: "customers who hit the file attach timeout",
    }),
    updateMacro(ctx, {
      parentId: shipId,
      question: "Did the file upload timeout get fixed?",
      answer: "Yes. The file attach timeout is fixed. Retry the upload from the shared inbox.",
    }),
  ]);
  return {
    chain: "shipped",
    plan_task_id: plan.task_id,
    ship_task_id: shipId,
    outreach_task_id: outreach.task_id,
    macro_task_id: macro.task_id,
  };
}

const PULSE_COPY =
  "Pulse Studio is a one-page product site for a small team. It explains the product and points buyers to support. This page is a mock and is not a store.";

export async function chainLaunch(ctx: ServiceCtx, input: { parentId?: string; timeoutMs?: number } = {}) {
  const engineering = ctx.clientFor("engineering");
  const productId = newId("product");
  const catalog = listingFromUpstream({
    taskId: "pulse-studio",
    output: {
      url: "/pulse",
      image_url: "/pulse",
      price: 49,
      product: {
        id: "pulse-studio",
        sku: "pulse-studio",
        title: "Pulse Studio",
        description: "A one-page product site for a small team.",
        tagline: "A one-page product site",
        product_type: "poster",
        price_usd: 49,
        cost_usd: 12,
        trend: "shared inbox",
        image: "/pulse",
        url: "/pulse",
      },
    },
  });
  await engineering.log({
    task_id: productId,
    ...(input.parentId ? { parent_id: input.parentId } : {}),
    status: "done",
    summary: `Product created: ${catalog.product.title}`,
    output: { kind: "product_created", product: catalog.product },
  });
  const pageId = newId("page");
  const drafted = await grokText(
    `Write one plain sentence describing ${catalog.product.title}, a one-page product site for a small team. Mention ${catalog.product.title}. No prices, no email, no phone, no promises.`,
  );
  const rawCopy = drafted.text || PULSE_COPY;
  const copy = rawCopy.includes(catalog.product.title) ? rawCopy : `${catalog.product.title}: ${rawCopy}`;
  const copyMode = drafted.mode;
  const page = await runCustomerGate({
    client: engineering,
    taskId: pageId,
    parentId: productId,
    kind: "public_post",
    content: copy,
    summary: "Checking the Pulse Studio landing page",
    deliver: "handoff",
    timeoutMs: input.timeoutMs,
    send: async () => {
      const dir = path.join(ctx.dataDir, "pulse");
      await mkdir(dir, { recursive: true });
      const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Pulse Studio</title></head><body><main><h1>Pulse Studio</h1><p>${copy}</p><p class="mode">${copyMode === "live" ? "LIVE" : "MOCK"}</p><p><a href="/panel">Ask support a question</a></p></main></body></html>`;
      await writeFile(path.join(dir, "index.html"), html);
      return { page: "/pulse", grok: copyMode, copy_mode: copyMode };
    },
  });
  const listingId = newId("listing");
  await ctx.clientFor("sales").log({
    task_id: listingId,
    parent_id: pageId,
    status: "done",
    summary: `${catalog.product.title} listing is live`,
    output: {
      kind: "listing_live",
      url: catalog.product.url,
      price: catalog.product.price_usd,
      title: catalog.product.title,
      copy,
      copy_mode: copyMode,
      product: catalog.product,
    },
  });
  const buyer = await draftReply(ctx, {
    parentId: listingId,
    timeoutMs: input.timeoutMs,
    message: {
      id: "msg_pulse_buyer",
      from_name: "Casey Nguyen",
      body: "What does Pulse Studio do, and how do I ask a question about it?",
      channel: "email",
    },
  });
  return {
    chain: "launch",
    product_task_id: productId,
    page_task_id: pageId,
    listing_task_id: listingId,
    support_task_id: buyer.task_id,
    qa_passed: page.verdict === "pass",
    listing_live: true,
    copy_mode: copyMode,
  };
}

export async function chainSignals(ctx: ServiceCtx, input: { timeoutMs?: number } = {}) {
  const timeoutMs = input.timeoutMs ?? 3000;
  const [plan, design] = await Promise.all([
    planIssue(ctx, { timeoutMs }),
    draftReply(ctx, { message_id: "msg_design", timeoutMs }),
  ]);
  return {
    chain: "signals",
    plan_task_id: plan.task_id,
    hire_task_id: plan.hire_task_id ?? null,
    design_task_id: design.task_id,
  };
}
