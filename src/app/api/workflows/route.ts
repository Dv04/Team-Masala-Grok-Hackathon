import { io } from "next/cache";
import { NextResponse } from "next/server";
import { listWorkflows } from "@/lib/services/workflow-service";
import { toApiError } from "@/lib/utils/errors";

export async function GET() {
  // Cache Components prerenders GET handlers that never touch a request-time
  // API. Workflow runs live in memory and must be read per request.
  await io();

  try {
    return NextResponse.json({
      ok: true,
      workflows: listWorkflows(),
    });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(apiError.body, {
      status: apiError.status,
    });
  }
}
