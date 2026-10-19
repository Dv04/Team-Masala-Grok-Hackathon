import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/tasks/route";
import { store } from "@/lib/data/in-memory-store";

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

  it("creates task and lists tasks", async () => {
    store.reset();

    const request = new NextRequest("http://localhost/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title: "Mock run",
        description: "Run local mock workflow",
        requestedBy: "Developer 2",
      }),
      headers: {
        "Content-Type": "application/json",
      },
    });

    const createResponse = await POST(request);
    const createBody = await createResponse.json();

    expect(createResponse.status).toBe(201);
    expect(createBody.ok).toBe(true);

    await new Promise((resolve) => setTimeout(resolve, 10));

    const listResponse = await GET();
    const listBody = await listResponse.json();

    expect(listResponse.status).toBe(200);
    expect(listBody.tasks.length).toBe(1);
  });
});
