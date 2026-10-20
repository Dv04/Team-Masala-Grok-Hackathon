function redactString(value: string): string {
  return value
    .replace(/\b(?:sk|xai|AKIA|ghp)[_-][A-Za-z0-9]{8,}\b/g, "[redacted]")
    .replace(/\b\d{3}-\d{2}-\d{4}\b/g, "[redacted]")
    .replace(/\b(?:\d[ -]?){13,19}\b/g, "[redacted]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[redacted]")
    .replace(/\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b/g, "[redacted]");
}

export function redactValue(value: unknown): unknown {
  if (typeof value === "string") return redactString(value);
  if (Array.isArray(value)) return value.map((item) => redactValue(item));
  if (!value || typeof value !== "object") return value;
  const out: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value)) {
    if (/email|phone|ssn|card|secret|token|api[_-]?key|password/i.test(key) && typeof child === "string") {
      out[key] = "[redacted]";
    } else {
      out[key] = redactValue(child);
    }
  }
  return out;
}

export function redactOutput(output: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (!output) return output;
  return redactValue(output) as Record<string, unknown>;
}
