import { NextResponse } from "next/server";
import { env } from "@/lib/config/env";

export async function GET() {
  return NextResponse.json({
    ok: true,
    service: "grokbot-hackathon-starter",
    mode: env.GROK_PROVIDER_MODE,
    timestamp: new Date().toISOString(),
  });
}
