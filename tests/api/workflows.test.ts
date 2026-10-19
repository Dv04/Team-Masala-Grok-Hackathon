import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { GET as listTasks, POST } from "@/app/api/tasks/route";
import { GET } from "@/app/api/workflows/route";
import { store } from "@/lib/data/in-memory-store";

async function waitFor<T>(
  read: () => Promise<T>,
  ready: (value: T) => boolean,
): Promise<T> {
  const started = Date.now();
  let latest = await read();
  while (!ready(latest)) {
    if (Date.now() - started > 1000) {
      throw new Error(
        `timed out waiting for workflow state: ${JSON.stringify(latest)}`,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
    latest = await read();
  }
  return latest;
}

describe("GET /api/workflows", () => {
  it("returns workflow collection", async () => {
    store.reset();
    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(Array.isArray(body.workflows)).toBe(true);
  });

  it("lists a workflow created by a submitted task", async () => {
    store.reset();
    const request = new NextRequest("http://localhost/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "Live workflow",
        description: "Show this run on the workflow list",
        requestedBy: "qa",
      }),
    });

    const createResponse = await POST(request);
    const created = await createResponse.json();

    expect(createResponse.status).toBe(201);
    expect(created.ok).toBe(true);

    const listed = await waitFor(
      async () => {
        const response = await GET();
        return { response, body: await response.json() };
      },
      ({ body }) =>
        Array.isArray(body.workflows) &&
        body.workflows.some(
          (workflow: { taskId?: string; status?: string }) =>
            workflow.taskId === created.task.id &&
            workflow.status === "succeeded",
        ),
    );

    expect(listed.response.status).toBe(200);
    const workflow = listed.body.workflows.find(
      (item: { id: string }) => item.id === created.task.workflowId,
    );
    expect(workflow).toMatchObject({
      id: created.task.workflowId,
      taskId: created.task.id,
      name: "LOCAL MOCK Workflow",
      status: "succeeded",
      currentStep: "complete",
      steps: ["orchestrate", "execute", "review"],
    });
    expect(
      workflow.timeline.map((message: { role: string }) => message.role),
    ).toEqual(["system", "agent", "agent", "agent"]);

    const tasksResponse = await listTasks();
    const tasksBody = await tasksResponse.json();
    expect(tasksBody.tasks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: created.task.id,
          status: "succeeded",
          result: "LOCAL MOCK workflow completed",
        }),
      ]),
    );
  });
});
