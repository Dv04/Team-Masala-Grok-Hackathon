import { withToolFallback } from "../tools/fallback.js";

export interface InboxMessage {
  id: string;
  from_name: string;
  body: string;
  channel: "email" | "chat";
}

export const INBOX: InboxMessage[] = [
  { id: "msg_ship", from_name: "Avery Quinn", body: "Hi, where is my order 1001?", channel: "email" },
  { id: "msg_refund", from_name: "Sam Okonkwo", body: "I want a refund for order 1001. It arrived damaged.", channel: "chat" },
  {
    id: "msg_bug",
    from_name: "Riley Chen",
    body: "The shared inbox throws a timeout when we attach a file. This looks like a bug in the uploader.",
    channel: "chat",
  },
  {
    id: "msg_design",
    from_name: "Jules Park",
    body: "Could you make a setup diagram we can put on the counter?",
    channel: "email",
  },
  {
    id: "msg_churn",
    from_name: "Nora Hale",
    body: "We may cancel next month. This is a churn risk, though a larger shared inbox would be an upsell.",
    channel: "email",
  },
];

export type Intent = "refund" | "pricing" | "design" | "bug" | "churn" | "question";

export function classify(body: string): Intent {
  if (/\b(churn|upsell|cancel)\b/i.test(body)) return "churn";
  if (/\brefund\b/i.test(body)) return "refund";
  if (/\b(price|pricing|discount)\b/i.test(body)) return "pricing";
  if (/\b(diagram|logo|banner|brand asset)\b/i.test(body)) return "design";
  if (/\b(bug|timeout|crash|exception)\b/i.test(body)) return "bug";
  return "question";
}

export interface SupportToolEnv {
  toolsMode: "live" | "mock";
  chatwootBaseUrl?: string;
  chatwootToken?: string;
  chatwootAccountId?: string;
  inboxZeroMcpUrl?: string;
  ragflowBaseUrl?: string;
  ragflowApiKey?: string;
}

export function supportEnvFrom(env: NodeJS.ProcessEnv = process.env): SupportToolEnv {
  const pick = (key: string) => env[key]?.trim() || undefined;
  return {
    toolsMode: env.TOOLS_MODE === "live" ? "live" : "mock",
    ...(pick("CHATWOOT_BASE_URL") ? { chatwootBaseUrl: pick("CHATWOOT_BASE_URL") } : {}),
    ...(pick("CHATWOOT_API_TOKEN") ? { chatwootToken: pick("CHATWOOT_API_TOKEN") } : {}),
    ...(pick("CHATWOOT_ACCOUNT_ID") ? { chatwootAccountId: pick("CHATWOOT_ACCOUNT_ID") } : {}),
    ...(pick("INBOX_ZERO_MCP_URL") ? { inboxZeroMcpUrl: pick("INBOX_ZERO_MCP_URL") } : {}),
    ...(pick("RAGFLOW_BASE_URL") ? { ragflowBaseUrl: pick("RAGFLOW_BASE_URL") } : {}),
    ...(pick("RAGFLOW_API_KEY") ? { ragflowApiKey: pick("RAGFLOW_API_KEY") } : {}),
  };
}

export interface SupportAdapters {
  listInbox(): Promise<InboxMessage[] & { mode: "live" | "mock" }>;
  retrieve(query: string, entries: { q: string; a: string }[]): Promise<{ hits: number; mode: "live" | "mock" }>;
}

export function createSupportAdapters(env: SupportToolEnv = supportEnvFrom()): SupportAdapters {
  const mock: SupportAdapters = {
    async listInbox() {
      return Object.assign(
        INBOX.map((message) => ({ ...message })),
        { mode: "mock" as const },
      );
    },
    async retrieve(_query, entries) {
      return { hits: entries.length, mode: "mock" };
    },
  };
  if (env.toolsMode !== "live") return mock;
  return {
    async listInbox() {
      return withToolFallback(
        Boolean(env.chatwootBaseUrl && env.chatwootToken && env.chatwootAccountId),
        async (signal) => {
          const response = await fetch(new URL(`/api/v1/accounts/${env.chatwootAccountId}/conversations`, env.chatwootBaseUrl), {
            headers: { api_access_token: env.chatwootToken ?? "" },
            signal,
          });
          if (!response.ok) throw new Error(`Chatwoot returned ${response.status}`);
          return Object.assign([] as InboxMessage[], { mode: "live" as const });
        },
        () => mock.listInbox(),
      );
    },
    async retrieve(query, entries) {
      return withToolFallback(
        Boolean(env.ragflowBaseUrl && env.ragflowApiKey),
        async (signal) => {
          const response = await fetch(new URL("/api/v1/retrieval", env.ragflowBaseUrl), {
            method: "POST",
            headers: { authorization: `Bearer ${env.ragflowApiKey}`, "content-type": "application/json" },
            body: JSON.stringify({ question: query || "faq" }),
            signal,
          });
          if (!response.ok) throw new Error(`RAGFlow returned ${response.status}`);
          return { hits: 0, mode: "live" as const };
        },
        () => mock.retrieve(query, entries),
      );
    },
  };
}
