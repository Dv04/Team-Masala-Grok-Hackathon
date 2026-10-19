import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/tasks/route";
import { store } from "@/lib/data/in-memory-store";
import { errorResponseSchema } from "@/lib/schemas/api";

const validTask = {
  title: "Mock run",
  description: "Run local mock workflow",
  requestedBy: "Developer 2",
};

async function postTask(body: unknown) {
  const request = new NextRequest("http://localhost/api/tasks", {
    method: "POST",
    body: JSON.stringify(body),
    headers: {
      "Content-Type": "application/json",
    },
  });
  const response = await POST(request);
  const payload = await response.json();
  return { response, payload };
}

describe("/api/tasks", () => {
  it("rejects invalid task input", async () => {
    store.reset();
    const request = new NextRequest("http://localhost/api/tasks", {
      method: "POST",
      body: JSON.stringify({ title: "x" }),
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe("INVALID_TASK_INPUT");
  });

  it.each([
    {
      name: "missing fields",
      body: {},
      fields: ["title", "description", "requestedBy"],
    },
    {
      name: "empty fields",
      body: { title: "", description: "", requestedBy: "" },
      fields: ["title", "description", "requestedBy"],
    },
    {
      name: "wrong-type fields",
      body: {
        title: 12,
        description: null,
        requestedBy: false,
        roleHints: "orchestrator",
      },
      fields: ["title", "description", "requestedBy", "roleHints"],
    },
  ])("returns 400 for $name", async ({ body, fields }) => {
    store.reset();
    const { response, payload } = await postTask(body);
    const parsed = errorResponseSchema.safeParse(payload);

    expect(response.status).toBe(400);
    expect(parsed.success).toBe(true);
    if (!parsed.success) {
      return;
    }

    expect(parsed.data.error.code).toBe("INVALID_TASK_INPUT");
    expect(parsed.data.error.message).toBe("Task input validation failed");

    const issues = parsed.data.error.details as {
      issues?: { path: PropertyKey[] }[];
    };
    const paths = (issues.issues ?? []).map((issue) => String(issue.path[0]));
    expect(paths).toEqual(expect.arrayContaining(fields));
    expect(store.listTasks()).toHaveLength(0);
  });

  it("creates task and lists tasks", async () => {
    store.reset();

    const { response: createResponse, payload: createBody } =
      await postTask(validTask);

    expect(createResponse.status).toBe(201);
    expect(createBody.ok).toBe(true);

    await new Promise((resolve) => setTimeout(resolve, 10));

    const listResponse = await GET();
    const listBody = await listResponse.json();

    expect(listResponse.status).toBe(200);
    expect(listBody.tasks.length).toBe(1);
  });
});
