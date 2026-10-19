import type { WorkflowRecord } from "@/types/domain";
import { StatusBadge } from "@/components/ui/status-badge";

export function WorkflowCard({ workflow }: { workflow: WorkflowRecord }) {
  return (
    <article className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-100">{workflow.name}</h3>
        <StatusBadge value={workflow.status} />
      </div>
      <p className="text-xs text-zinc-400">Current step: {workflow.currentStep}</p>
    </article>
  );
}
