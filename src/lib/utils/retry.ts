export interface RetryOptions {
  retries: number;
  delayMs?: number;
  retryIf?: (error: unknown, attempt: number) => boolean;
}

export async function withRetry<T>(
  operation: () => Promise<T>,
  options: RetryOptions,
): Promise<T> {
  const { retries, delayMs = 0, retryIf = () => true } = options;
  let attempt = 0;

  while (true) {
    try {
      return await operation();
    } catch (error) {
      if (attempt >= retries || !retryIf(error, attempt + 1)) {
        throw error;
      }
      attempt += 1;
      if (delayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
}
