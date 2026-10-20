import type { Dept } from "../config.js";
import type { DepartmentClient } from "../contract/client.js";

export interface ServiceCtx {
  dataDir: string;
  mode: "live" | "mock";
  clientFor(dept: Dept): DepartmentClient;
}
