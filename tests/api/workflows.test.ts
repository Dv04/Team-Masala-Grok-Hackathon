import { describe, expect, it } from "vitest";
import { GET } from "@/app/api/workflows/route";
import { store } from "@/lib/data/in-memory-store";

describe("GET /api/workflows", () => {
  it("returns workflow collection", async () => {
    store.reset();
    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(Array.isArray(body.workflows)).toBe(true);
  });
});
