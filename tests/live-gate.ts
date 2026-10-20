/** Live vitest suites (port 8810, live Grok, approvals, listing publish) run only when this is set. */
export function liveSuitesEnabled(): boolean {
  return process.env.RUN_LIVE === "1";
}
