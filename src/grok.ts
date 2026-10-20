export async function grokText(prompt: string): Promise<{ text: string; mode: "live" | "mock" }> {
  const key = process.env.XAI_API_KEY?.trim();
  if (!key) return { text: "", mode: "mock" };
  const response = await fetch("https://api.x.ai/v1/responses", {
    method: "POST",
    headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify({ model: process.env.XAI_MODEL?.trim() || "grok-4", input: prompt }),
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(`xAI responses returned ${response.status}`);
  const body = (await response.json()) as { output_text?: string; output?: Array<{ content?: Array<{ text?: string }> }> };
  const nested = body.output?.flatMap((item) => item.content ?? []).map((part) => part.text ?? "").join("").trim();
  const text = (body.output_text ?? nested ?? "").trim();
  if (!text) throw new Error("xAI responses returned no text");
  return { text, mode: "live" };
}
