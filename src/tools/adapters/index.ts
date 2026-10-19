import { toolRegistry } from "@/tools/core/tool-registry";
import { LocalEchoTool } from "@/tools/adapters/local-echo-tool";

let initialized = false;

export function registerDefaultTools(): void {
  if (initialized) {
    return;
  }

  toolRegistry.register(new LocalEchoTool());
  initialized = true;
}
