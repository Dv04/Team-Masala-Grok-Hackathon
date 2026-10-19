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

  it("gives up after the maximum attempts and surfaces the original error", async () => {
    const error = new Error("permanent failure");
    let attempts = 0;

    await expect(
      withRetry(
        async () => {
          attempts += 1;
          throw error;
        },
        { retries: 2 },
      ),
    ).rejects.toBe(error);

    expect(attempts).toBe(3);
  });

  it("does not keep retrying when retryIf rejects the error", async () => {
    let attempts = 0;

    await expect(
      withRetry(
        async () => {
          attempts += 1;
          throw new Error("do not retry");
        },
        {
          retries: 4,
          retryIf: () => false,
        },
      ),
    ).rejects.toThrow("do not retry");

    expect(attempts).toBe(1);
  });
});
