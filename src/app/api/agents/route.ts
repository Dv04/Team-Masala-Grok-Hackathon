import { NextResponse } from "next/server";
import { listAgents } from "@/lib/services/agent-service";
import { toApiError } from "@/lib/utils/errors";

export async function GET() {
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
