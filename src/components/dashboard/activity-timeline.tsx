import type { WorkflowRecord } from "@/types/domain";

export function ActivityTimeline({ workflows }: { workflows: WorkflowRecord[] }) {
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
      <h2 className="mb-3 text-sm font-semibold text-zinc-100">Activity timeline</h2>
      {workflows.length === 0 ? (
        <p className="text-sm text-zinc-500">No workflow events yet.</p>
      ) : (
        <ul className="space-y-2">
          {workflows.slice(0, 3).map((workflow) => (
            <li key={workflow.id} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2">
              <p className="text-xs text-zinc-300">{workflow.name}</p>
              <p className="text-[11px] text-zinc-500">
                {workflow.currentStep} · {workflow.status} · {workflow.updatedAt}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
