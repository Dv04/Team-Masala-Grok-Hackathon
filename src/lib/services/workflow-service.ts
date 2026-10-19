import { store } from "@/lib/data/in-memory-store";

export function listWorkflows() {
  return store.listWorkflows();
}
