export interface McpTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  handler: (args: Record<string, unknown>) => Promise<unknown>;
}

interface Rpc {
  jsonrpc?: string;
  id?: string | number | null;
  method?: string;
  params?: { name?: string; arguments?: Record<string, unknown>; protocolVersion?: string; clientInfo?: { name?: string } };
}

export async function handleMcp(body: unknown, tools: McpTool[], serverName: string): Promise<{ status: number; json: unknown | null }> {
  if (!body || typeof body !== "object") return { status: 400, json: rpcError(null, -32700, "Parse error") };
  const rpc = body as Rpc;
  if (!rpc.method) return { status: 400, json: rpcError(rpc.id ?? null, -32600, "Invalid request") };
  if (rpc.id === undefined || rpc.id === null) return { status: 202, json: null };
  if (rpc.method === "initialize") {
    return {
      status: 200,
      json: {
        jsonrpc: "2.0",
        id: rpc.id,
        result: {
          protocolVersion: "2025-03-26",
          capabilities: { tools: { listChanged: false } },
          serverInfo: { name: serverName, version: "0.1.0" },
        },
      },
    };
  }
  if (rpc.method === "ping") return { status: 200, json: { jsonrpc: "2.0", id: rpc.id, result: {} } };
  if (rpc.method === "tools/list") {
    return {
      status: 200,
      json: {
        jsonrpc: "2.0",
        id: rpc.id,
        result: {
          tools: tools.map((tool) => ({ name: tool.name, description: tool.description, inputSchema: tool.inputSchema })),
        },
      },
    };
  }
  if (rpc.method === "tools/call") {
    const name = rpc.params?.name;
    const tool = tools.find((item) => item.name === name);
    if (!tool) return { status: 200, json: rpcError(rpc.id, -32602, `Unknown tool ${name}`) };
    try {
      const value = await tool.handler(rpc.params?.arguments ?? {});
      return {
        status: 200,
        json: {
          jsonrpc: "2.0",
          id: rpc.id,
          result: {
            content: [{ type: "text", text: JSON.stringify(value) }],
            structuredContent: value,
          },
        },
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Tool failed";
      return {
        status: 200,
        json: {
          jsonrpc: "2.0",
          id: rpc.id,
          result: { content: [{ type: "text", text: message }], isError: true },
        },
      };
    }
  }
  return { status: 200, json: rpcError(rpc.id, -32601, `Method not found: ${rpc.method}`) };
}

function rpcError(id: string | number | null, code: number, message: string) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}
