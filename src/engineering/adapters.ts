import { withToolFallback } from "../tools/fallback.js";

export interface Issue {
  number: number;
  title: string;
  body: string;
  labels: string[];
  needs_hire?: boolean;
}

export const ISSUE_FIXTURE: Issue = {
  number: 42,
  title: "Checkout times out when the queue backs up",
  body: "Requests over two seconds fail once the queue is full. We need to hire a backend engineer to own the worker.",
  labels: ["bug", "hire"],
  needs_hire: true,
};

export interface EngineeringToolEnv {
  toolsMode: "live" | "mock";
  openhandsBaseUrl?: string;
  openhandsApiKey?: string;
  githubToken?: string;
  githubIssue?: string;
}

export function engineeringEnvFrom(env: NodeJS.ProcessEnv = process.env): EngineeringToolEnv {
  const pick = (key: string) => env[key]?.trim() || undefined;
  return {
    toolsMode: env.TOOLS_MODE === "live" ? "live" : "mock",
    ...(pick("OPENHANDS_BASE_URL") ? { openhandsBaseUrl: pick("OPENHANDS_BASE_URL") } : {}),
    ...(pick("OPENHANDS_API_KEY") ? { openhandsApiKey: pick("OPENHANDS_API_KEY") } : {}),
    ...(pick("GITHUB_TOKEN") ? { githubToken: pick("GITHUB_TOKEN") } : {}),
    ...(pick("GITHUB_ISSUE") ? { githubIssue: pick("GITHUB_ISSUE") } : {}),
  };
}

export interface EngineeringAdapters {
  getIssue(override?: Issue): Promise<{ issue: Issue; mode: "live" | "mock" }>;
  startConversation(issue: Issue): Promise<{ conversation_id: string; mode: "live" | "mock" }>;
}

export function createEngineeringAdapters(env: EngineeringToolEnv = engineeringEnvFrom()): EngineeringAdapters {
  const mock: EngineeringAdapters = {
    async getIssue(override) {
      return { issue: override ?? { ...ISSUE_FIXTURE, labels: [...ISSUE_FIXTURE.labels] }, mode: "mock" };
    },
    async startConversation() {
      return { conversation_id: "mock-conv-42", mode: "mock" };
    },
  };
  if (env.toolsMode !== "live") return mock;
  return {
    async getIssue(override) {
      if (override) return { issue: override, mode: "live" };
      return withToolFallback(
        Boolean(env.githubToken && env.githubIssue),
        async (signal) => {
          const match = /^([^/]+)\/([^#]+)#(\d+)$/.exec(env.githubIssue ?? "");
          if (!match) throw new Error("GITHUB_ISSUE must look like owner/repo#123");
          const response = await fetch(`https://api.github.com/repos/${match[1]}/${match[2]}/issues/${match[3]}`, {
            headers: { authorization: `Bearer ${env.githubToken}`, accept: "application/vnd.github+json" },
            signal,
          });
          if (!response.ok) throw new Error(`GitHub returned ${response.status}`);
          const body = (await response.json()) as { number: number; title: string; body: string; labels: { name: string }[] };
          return {
            issue: {
              number: body.number,
              title: body.title,
              body: body.body || "",
              labels: (body.labels || []).map((label) => label.name),
            },
            mode: "live" as const,
          };
        },
        () => mock.getIssue(),
      );
    },
    async startConversation(issue) {
      return withToolFallback(
        Boolean(env.openhandsBaseUrl && env.openhandsApiKey),
        async (signal) => {
          const response = await fetch(new URL("/api/conversations", env.openhandsBaseUrl), {
            method: "POST",
            headers: { authorization: `Bearer ${env.openhandsApiKey}`, "content-type": "application/json" },
            body: JSON.stringify({}),
            signal,
          });
          if (!response.ok) throw new Error(`OpenHands returned ${response.status}`);
          const body = (await response.json()) as { conversation_id?: string; id?: string };
          return { conversation_id: body.conversation_id || body.id || "live", mode: "live" as const };
        },
        () => mock.startConversation(issue),
      );
    },
  };
}

export function wantsHire(issue: Issue): boolean {
  if (issue.needs_hire) return true;
  const text = `${issue.title} ${issue.body} ${issue.labels.join(" ")}`;
  return /\b(hire|hiring|headcount|staffing)\b/i.test(text);
}
