/** Canned Grok reply. Shown until XAI_API_KEY is set; the same function then calls the live API. */
export const GROK_MOCK_TEXT =
  "MOCK Grok: Pulse Studio is a one-page product site for a small team. It explains the product and points buyers to support. No model wrote this sentence.";

export async function grokText(prompt: string): Promise<{ text: string; mode: "live" | "mock" }> {
  const key = process.env.XAI_API_KEY?.trim();
  if (!key) return { text: GROK_MOCK_TEXT, mode: "mock" };
  try {
    const response = await fetch("https://api.x.ai/v1/responses", {
      method: "POST",
      headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
      body: JSON.stringify({
        model: process.env.XAI_MODEL?.trim() || "grok-4",
        input: prompt,
      }),
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) return { text: GROK_MOCK_TEXT, mode: "mock" };
    const body = (await response.json()) as { output_text?: string; output?: Array<{ content?: Array<{ text?: string }> }> };
    const nested = body.output
      ?.flatMap((item) => item.content ?? [])
      .map((part) => part.text ?? "")
      .join("")
      .trim();
    const text = (body.output_text ?? nested ?? "").trim();
    if (!text) return { text: GROK_MOCK_TEXT, mode: "mock" };
    return { text, mode: "live" };
  } catch (error) {
    console.error("xAI call failed; using MOCK", error instanceof Error ? error.message : error);
    return { text: GROK_MOCK_TEXT, mode: "mock" };
  }
}
