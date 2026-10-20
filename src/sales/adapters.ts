import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { withToolFallback } from "../tools/fallback.js";

export interface Lead {
  id: string;
  name: string;
  title: string;
  company: string;
  domain: string;
  email: string;
  score: number;
  question?: string;
  emailStatus?: "valid" | "invalid";
}

export interface ToolEnv {
  toolsMode: "live" | "mock";
  twentyBaseUrl?: string;
  twentyApiKey?: string;
  openoutreachBin?: string;
  reacherBaseUrl?: string;
  warmblyBaseUrl?: string;
  warmblyApiKey?: string;
}

export function toolEnvFrom(env: NodeJS.ProcessEnv = process.env): ToolEnv {
  const pick = (key: string) => {
    const value = env[key]?.trim();
    return value ? value : undefined;
  };
  return {
    toolsMode: env.TOOLS_MODE === "live" ? "live" : "mock",
    ...(pick("TWENTY_BASE_URL") ? { twentyBaseUrl: pick("TWENTY_BASE_URL") } : {}),
    ...(pick("TWENTY_API_KEY") ? { twentyApiKey: pick("TWENTY_API_KEY") } : {}),
    ...(pick("OPENOUTREACH_BIN") ? { openoutreachBin: pick("OPENOUTREACH_BIN") } : {}),
    ...(pick("REACHER_BASE_URL") ? { reacherBaseUrl: pick("REACHER_BASE_URL") } : {}),
    ...(pick("WARMBLY_BASE_URL") ? { warmblyBaseUrl: pick("WARMBLY_BASE_URL") } : {}),
    ...(pick("WARMBLY_API_KEY") ? { warmblyApiKey: pick("WARMBLY_API_KEY") } : {}),
  };
}

const reacherCache = new Map<string, { at: number; value: { is_reachable: "safe" | "invalid"; mode: "mock" } }>();

const POOL: Lead[] = [
  {
    id: "lead_priya",
    name: "Priya Shah",
    title: "Owner",
    company: "Lamppost Coffee",
    domain: "lamppost.example",
    email: "priya@lamppost.example",
    score: 0.91,
    question: "Does Masala Desk keep a shared inbox for a three-person roasting team?",
  },
  {
    id: "lead_mateo",
    name: "Mateo Alvarez",
    title: "Founder",
    company: "Rio Roast",
    domain: "rioroast.example",
    email: "mateo@rioroast.example",
    score: 0.84,
  },
  {
    id: "lead_helen",
    name: "Helen Cho",
    title: "General manager",
    company: "Batch and Bean",
    domain: "batchbean.example",
    email: "helen@batchbean.example",
    score: 0.8,
  },
];

export interface SalesAdapters {
  openoutreach: { find(icp: string, limit: number): Promise<Lead[] & { mode: "live" | "mock" }> };
  reacher: { check(email: string): Promise<{ is_reachable: "safe" | "invalid"; mode: "live" | "mock" }> };
  twenty: { upsertPerson(lead: Lead): Promise<{ id: string; mode: "live" | "mock" }> };
  warmbly: { enroll(lead: Lead): Promise<{ provider: "warmbly"; mode: "live" | "mock"; sequence: string }> };
  crm: { write(dataDir: string, leads: Lead[]): Promise<void> };
}

export function createSalesAdapters(env: ToolEnv = toolEnvFrom()): SalesAdapters {
  const mock: SalesAdapters = {
    openoutreach: {
      async find(icp, limit) {
        const leads = POOL.slice(0, Math.max(1, Math.min(limit, POOL.length))).map((lead) => ({
          ...lead,
          score: icp ? lead.score : lead.score,
        }));
        return Object.assign(leads, { mode: "mock" as const });
      },
    },
    reacher: {
      async check(email) {
        const cached = reacherCache.get(email);
        if (cached && Date.now() - cached.at < 30_000) return cached.value;
        const safe = email.endsWith(".example") || email.endsWith("@example.com");
        const value = { is_reachable: safe ? ("safe" as const) : ("invalid" as const), mode: "mock" as const };
        reacherCache.set(email, { at: Date.now(), value });
        return value;
      },
    },
    twenty: {
      async upsertPerson(lead) {
        return { id: `twenty_${lead.id}`, mode: "mock" };
      },
    },
    warmbly: {
      async enroll() {
        return { provider: "warmbly", mode: "mock", sequence: "first-touch" };
      },
    },
    crm: { write: writeCrm },
  };

  if (env.toolsMode !== "live") return mock;

  return {
    openoutreach: {
      async find(icp, limit) {
        return withToolFallback(
          Boolean(env.openoutreachBin),
          (signal) => liveOpenoutreach(env.openoutreachBin as string, icp, limit, signal),
          () => mock.openoutreach.find(icp, limit),
        );
      },
    },
    reacher: {
      async check(email) {
        return withToolFallback(
          Boolean(env.reacherBaseUrl),
          async (signal) => {
            const response = await fetch(new URL("/v0/check_email", env.reacherBaseUrl), {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ to_email: email }),
              signal,
            });
            if (!response.ok) throw new Error(`Reacher returned ${response.status}`);
            const body = (await response.json()) as { is_reachable?: string };
            return { is_reachable: body.is_reachable === "safe" ? ("safe" as const) : ("invalid" as const), mode: "live" as const };
          },
          () => mock.reacher.check(email),
        );
      },
    },
    twenty: {
      async upsertPerson(lead) {
        return withToolFallback(
          Boolean(env.twentyBaseUrl && env.twentyApiKey),
          async (signal) => {
            const response = await fetch(new URL("/rest/people", env.twentyBaseUrl), {
              method: "POST",
              headers: { authorization: `Bearer ${env.twentyApiKey}`, "content-type": "application/json" },
              body: JSON.stringify({ name: lead.name, company: lead.company }),
              signal,
            });
            if (!response.ok) throw new Error(`Twenty returned ${response.status}`);
            const body = (await response.json()) as { id?: string };
            return { id: body.id || lead.id, mode: "live" as const };
          },
          () => mock.twenty.upsertPerson(lead),
        );
      },
    },
    warmbly: {
      async enroll(lead) {
        return withToolFallback(
          Boolean(env.warmblyBaseUrl && env.warmblyApiKey),
          async (signal) => {
            const response = await fetch(new URL("/api/v1/sequences/enroll", env.warmblyBaseUrl), {
              method: "POST",
              headers: { authorization: `Bearer ${env.warmblyApiKey}`, "content-type": "application/json" },
              body: JSON.stringify({ sequence: "first-touch" }),
              signal,
            });
            if (!response.ok) throw new Error(`Warmbly returned ${response.status}`);
            return { provider: "warmbly" as const, mode: "live" as const, sequence: "first-touch" };
          },
          () => mock.warmbly.enroll(lead),
        );
      },
    },
    crm: { write: writeCrm },
  };
}

async function liveOpenoutreach(bin: string, icp: string, limit: number, signal: AbortSignal): Promise<Lead[] & { mode: "live" }> {
  // find only. send and run stay disabled so outreach cannot leave this adapter.
  const output = await new Promise<string>((resolve, reject) => {
    const child = spawn(bin, ["find", String(limit), "--json"], {
      stdio: ["ignore", "pipe", "pipe"],
      signal,
    });
    let text = "";
    let settled = false;
    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      fn();
    };
    child.stdout.on("data", (chunk) => {
      text += String(chunk);
    });
    child.on("error", (error) => settle(() => reject(error)));
    child.on("close", (code) => settle(() => (code === 0 ? resolve(text) : reject(new Error(`openoutreach find exited ${code}`)))));
  });
  const leads = output
    .split("\n")
    .filter(Boolean)
    .slice(0, limit)
    .map((line, index) => {
      const row = JSON.parse(line) as Partial<Lead>;
      return {
        id: row.id || `live_${index}`,
        name: row.name || "Unknown",
        title: row.title || "",
        company: row.company || "",
        domain: row.domain || "",
        email: row.email || "",
        score: row.score ?? 0,
        ...(icp ? {} : {}),
      };
    });
  return Object.assign(leads, { mode: "live" as const });
}

function csv(value: string | number): string {
  const text = String(value);
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

export async function writeCrm(dataDir: string, leads: Lead[]): Promise<void> {
  const dir = path.join(dataDir, "crm");
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, "leads.json"), JSON.stringify(leads, null, 2));
  const header = "id,name,title,company,domain,email,score,email_status";
  const lines = leads.map((lead) =>
    [lead.id, lead.name, lead.title, lead.company, lead.domain, lead.email, lead.score, lead.emailStatus ?? ""].map(csv).join(","),
  );
  await writeFile(path.join(dir, "leads.csv"), `${header}\n${lines.join("\n")}\n`);
}

export function publicLead(lead: Lead): Record<string, unknown> {
  return {
    id: lead.id,
    name: lead.name,
    title: lead.title,
    company: lead.company,
    domain: lead.domain,
    score: lead.score,
    email_status: lead.emailStatus ?? "unknown",
  };
}
