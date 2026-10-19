import { z } from "zod";

const envSchema = z.object({
  GROK_PROVIDER_MODE: z.enum(["mock", "xai"]).default("mock"),
  XAI_API_KEY: z.string().optional(),
  XAI_BASE_URL: z.string().url().default("https://api.x.ai/v1"),
});

const parsed = envSchema.safeParse({
  GROK_PROVIDER_MODE: process.env.GROK_PROVIDER_MODE ?? "mock",
  XAI_API_KEY: process.env.XAI_API_KEY,
  XAI_BASE_URL: process.env.XAI_BASE_URL ?? "https://api.x.ai/v1",
});

if (!parsed.success) {
  throw new Error(`Invalid environment configuration: ${parsed.error.message}`);
}

export const env = parsed.data;
