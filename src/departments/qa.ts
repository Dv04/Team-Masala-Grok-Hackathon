import type { QaRequest, QaResponse } from "../contract/types.js";

export interface FailCounter {
  fails(taskId: string): number;
  recordFail(taskId: string): void;
}

const CHECKS = ["rubric", "factuality", "pii", "policy"];

const FOUNDER_KINDS = new Set(["refund", "payment", "discount", "legal", "pricing"]);

function hasPlaceholder(content: string): boolean {
  return /\[(?:TODO|NAME|COMPANY|INSERT)\]|\{\{[^}]+\}\}|lorem ipsum|\bPLACEHOLDER\b|\bTBD\b|\bX{3,}\b/i.test(
    content,
  );
}

function hasPii(content: string): boolean {
  return (
    /\b\d{3}-\d{2}-\d{4}\b/.test(content) ||
    /\b(?:sk|xai|AKIA|ghp)[_-][A-Za-z0-9]{8,}\b/.test(content) ||
    /\b\d{4}(?:[ -]\d{4}){3}\b/.test(content)
  );
}

function hasEmail(content: string): boolean {
  return /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(content);
}

function hasPhone(content: string): boolean {
  return /\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b/.test(content);
}

function isJson(content: string): boolean {
  try {
    const parsed = JSON.parse(content);
    return parsed !== null && typeof parsed === "object";
  } catch {
    return false;
  }
}

function firstContact(context: QaRequest["context"]): boolean {
  if (!context || typeof context !== "object" || Array.isArray(context)) return true;
  return context.first_contact !== false;
}

function clampScore(score: number): number {
  return Math.max(0, Math.min(1, Math.round(score * 100) / 100));
}

export function qaKindForOutput(output: Record<string, unknown>): string {
  if (typeof output.qa_kind === "string" && output.qa_kind.trim()) return output.qa_kind;
  if (output.kind === "design_request") return "public_post";
  if (output.kind === "hire_needed") return "internal";
  if (typeof output.kind === "string" && output.kind.trim()) return output.kind;
  return "internal";
}

export function evaluateQa(counter: FailCounter, req: QaRequest): QaResponse {
  const checks = [...CHECKS];
  const content = typeof req.content === "string" ? req.content : JSON.stringify(req.content ?? "");
  const reasons: string[] = [];
  let score = 0.95;
  const qaRequestId = typeof (req as QaRequest & { qa_request_id?: string }).qa_request_id === "string"
    ? (req as QaRequest & { qa_request_id?: string }).qa_request_id
    : undefined;

  if (!content.trim()) {
    reasons.push("empty content");
    score = 0;
  } else {
    const trimmed = content.trim();
    if ((trimmed.startsWith("{") || trimmed.startsWith("[")) && !isJson(trimmed)) {
      reasons.push("invalid JSON");
      score = 0.15;
    }
    if (hasPlaceholder(content)) {
      reasons.push("placeholder text");
      score -= 0.4;
    }
    if (hasPii(content)) {
      reasons.push("PII or secret detected");
      score -= 0.5;
    }
    if (req.kind === "public_post" && (hasEmail(content) || hasPhone(content))) {
      reasons.push("email or phone in a public post");
      score -= 0.5;
    }
    if (!reasons.length && content.trim().length < 12) {
      score = Math.min(score, 0.6);
    }
  }

  score = clampScore(score);

  if (reasons.length) {
    if (counter.fails(req.task_id) >= 1) {
      return {
        verdict: "founder",
        score: Math.min(score, 0.6),
        reasons: [...reasons, "second failure on the same task"],
        checks,
        ...(qaRequestId ? { qa_request_id: qaRequestId } : {}),
      };
    }
    counter.recordFail(req.task_id);
    return {
      verdict: "fail",
      score,
      reasons,
      checks,
      ...(qaRequestId ? { qa_request_id: qaRequestId } : {}),
    };
  }

  const founderReasons: string[] = [];
  if (FOUNDER_KINDS.has(req.kind)) founderReasons.push(`${req.kind} requires founder approval`);
  const explicitFirst = req.first_contact;
  const isFirst = explicitFirst === undefined ? firstContact(req.context) : explicitFirst !== false;
  if (req.kind === "outbound_email" && isFirst) {
    founderReasons.push("first-contact outbound email requires founder approval");
  }
  if (score < 0.7) founderReasons.push("score below 0.7");
  if (founderReasons.length) {
    return {
      verdict: "founder",
      score,
      reasons: founderReasons,
      checks,
      ...(qaRequestId ? { qa_request_id: qaRequestId } : {}),
    };
  }

  return {
    verdict: "pass",
    score,
    reasons: [],
    checks,
    ...(qaRequestId ? { qa_request_id: qaRequestId } : {}),
  };
}

export function reviseContent(content: string, reasons: string[]): string {
  let next = content;
  if (reasons.some((reason) => /placeholder/i.test(reason))) {
    next = next
      .replace(/\[(?:TODO|NAME|COMPANY|INSERT)\]/gi, "")
      .replace(/\{\{[^}]+\}\}/g, "")
      .replace(/lorem ipsum/gi, "")
      .replace(/\bPLACEHOLDER\b/gi, "")
      .replace(/\bTBD\b/g, "")
      .replace(/\bX{3,}\b/g, "")
      .replace(/[ \t]{2,}/g, " ")
      .trim();
  }
  if (reasons.some((reason) => /PII|secret/i.test(reason))) {
    next = next
      .replace(/\b\d{3}-\d{2}-\d{4}\b/g, "")
      .replace(/\b(?:sk|xai|AKIA|ghp)[_-][A-Za-z0-9]{8,}\b/g, "")
      .replace(/\b\d{4}(?:[ -]\d{4}){3}\b/g, "")
      .replace(/[ \t]{2,}/g, " ")
      .trim();
  }
  if (reasons.some((reason) => /invalid JSON/i.test(reason))) {
    return JSON.stringify({ note: "Revised after invalid JSON." });
  }
  if (reasons.some((reason) => /empty content/i.test(reason))) {
    return "Thanks for your message. A teammate will follow up with the details shortly.";
  }
  return next;
}
