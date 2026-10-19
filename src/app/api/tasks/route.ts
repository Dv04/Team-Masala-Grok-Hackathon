import { io } from "next/cache";
import { NextRequest, NextResponse } from "next/server";
import { createTask, listTasks } from "@/lib/services/task-service";
import { toApiError } from "@/lib/utils/errors";

export async function GET() {
  // POST already keeps this route dynamic. Opt the read out explicitly so a
  // future GET-only change cannot freeze the in-memory task list at build time.
  await io();

  try {
    const tasks = listTasks();
    return NextResponse.json({
      ok: true,
      tasks,
    });
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(apiError.body, {
      status: apiError.status,
    });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const task = await createTask(body);
    return NextResponse.json(
      {
        ok: true,
        task,
      },
      { status: 201 },
    );
  } catch (error) {
    const apiError = toApiError(error);
    return NextResponse.json(apiError.body, {
      status: apiError.status,
    });
  }
}
