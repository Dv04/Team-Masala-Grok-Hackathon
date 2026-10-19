import { io } from "next/cache";
import { NextResponse } from "next/server";
import { listAgents } from "@/lib/services/agent-service";
import { toApiError } from "@/lib/utils/errors";

export async function GET() {
  // Cache Components prerenders GET handlers that never touch a request-time
  // API. The registry is in-memory and can change after startup.
  await io();

  try {
    const agents = listAgents();
    return NextResponse.json({
      ok: true,
      agents,
    });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(apiError.body, {
      status: apiError.status,
    });
  }
}
