# Agent Integration

## Contract

Implement the `Agent` interface in `src/agents/core/types.ts`:

- receives `AgentExecutionContext`
- returns `AgentExecutionResult`
- uses `ToolRuntime` for tool invocations

## Provider modes

- `mock`: fully local deterministic adapter (`MockGrokAgent`)
- `xai`: placeholder adapter (`XaiGrokAgent`) that validates required env vars and returns explicit not-configured errors until official flow is wired.

Never expose API keys to client components.
