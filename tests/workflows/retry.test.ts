import { describe, expect, it } from "vitest";
import { withRetry } from "@/lib/utils/retry";

describe("withRetry", () => {
  it("retries failed operations and then succeeds", async () => {
    let attempts = 0;
    const result = await withRetry(
      async () => {
        attempts += 1;
        if (attempts < 2) {
          throw new Error("fail once");
        }
        return "ok";
      },
      { retries: 2 },
    );

    expect(result).toBe("ok");
    expect(attempts).toBe(2);
  });
});
