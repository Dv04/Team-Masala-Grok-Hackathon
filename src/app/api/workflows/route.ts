import { NextResponse } from "next/server";
import { listWorkflows } from "@/lib/services/workflow-service";
import { toApiError } from "@/lib/utils/errors";

export async function GET() {
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
