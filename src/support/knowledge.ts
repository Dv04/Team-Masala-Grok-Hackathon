import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { newId } from "../ids.js";
import type { ServiceCtx } from "../service/types.js";

export interface FaqEntry {
  id: string;
  q: string;
  a: string;
  tags: string[];
  published?: boolean;
}

export const FAQ_SEED: FaqEntry[] = [
  {
    id: "ship",
    q: "Where is my order?",
    a: "Orders ship within two business days. You can check the status on your Masala Desk account page.",
    tags: ["shipping", "order"],
  },
  {
    id: "shared",
    q: "Does Masala Desk support a shared inbox?",
    a: "Yes. A three-person team can share one inbox, assign notes, and keep the founder in the approval loop.",
    tags: ["shared", "inbox", "team"],
  },
  {
    id: "returns",
    q: "How do returns work?",
    a: "Returns are accepted within 30 days from the account page. Refunds stay pending until a founder approves them.",
    tags: ["returns", "refund"],
  },
  {
    id: "pricing",
    q: "Can you change the price?",
    a: "Pricing changes wait for founder approval. I can file the request and nothing changes until then.",
    tags: ["pricing"],
  },
];

const faqCache = new Map<string, { at: number; entries: FaqEntry[] }>();
const FAQ_TTL_MS = 5000;

export async function loadFaq(dataDir: string): Promise<FaqEntry[]> {
  const cached = faqCache.get(dataDir);
  if (cached && Date.now() - cached.at < FAQ_TTL_MS) return cached.entries.map((entry) => ({ ...entry, tags: [...entry.tags] }));
  const file = path.join(dataDir, "support", "faq.json");
  let entries: FaqEntry[];
  try {
    entries = JSON.parse(await readFile(file, "utf8")) as FaqEntry[];
  } catch {
    await mkdir(path.dirname(file), { recursive: true });
    entries = FAQ_SEED.map((entry) => ({ ...entry, tags: [...entry.tags] }));
    await writeFile(file, JSON.stringify(entries, null, 2));
  }
  faqCache.set(dataDir, { at: Date.now(), entries });
  return entries.map((entry) => ({ ...entry, tags: [...entry.tags] }));
}

export async function saveFaq(dataDir: string, entries: FaqEntry[]): Promise<void> {
  const file = path.join(dataDir, "support", "faq.json");
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, JSON.stringify(entries, null, 2));
  faqCache.set(dataDir, { at: Date.now(), entries });
}

export function searchFaq(entries: FaqEntry[], query: string): FaqEntry[] {
  const tokens = query.toLowerCase().split(/[^a-z0-9]+/).filter((token) => token.length > 3);
  return entries
    .map((entry) => ({
      entry,
      score: tokens.filter((token) => `${entry.q} ${entry.a} ${entry.tags.join(" ")}`.toLowerCase().includes(token)).length,
    }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((row) => row.entry);
}

export async function recordLeadQuestion(
  ctx: ServiceCtx,
  args: { question: string; company: string; leadId: string; parentId: string },
): Promise<{ task_id: string; matched: boolean; faq_id?: string }> {
  const client = ctx.clientFor("support");
  const taskId = newId("know");
  await client.log({
    task_id: taskId,
    parent_id: args.parentId,
    status: "running",
    summary: `Looking up a question from ${args.company}`,
    output: { lead_id: args.leadId, company: args.company },
  });
  const hits = searchFaq(await loadFaq(ctx.dataDir), args.question);
  const hit = hits[0];
  if (hit) {
    await client.log({
      task_id: taskId,
      parent_id: args.parentId,
      status: "done",
      summary: `Answered a sales lead from the support FAQ`,
      output: { kind: "knowledge", lead_id: args.leadId, company: args.company, faq_id: hit.id, matched: true },
    });
    return { task_id: taskId, matched: true, faq_id: hit.id };
  }
  const entries = await loadFaq(ctx.dataDir);
  const created: FaqEntry = {
    id: newId("faq"),
    q: args.question,
    a: "We will confirm this with the founder and add it to the help center after review.",
    tags: ["draft"],
    published: false,
  };
  entries.push(created);
  await saveFaq(ctx.dataDir, entries);
  await client.log({
    task_id: taskId,
    parent_id: args.parentId,
    status: "done",
    summary: "Filed a new FAQ draft from a sales question",
    output: { kind: "knowledge", lead_id: args.leadId, company: args.company, faq_id: created.id, matched: false },
  });
  return { task_id: taskId, matched: false, faq_id: created.id };
}
