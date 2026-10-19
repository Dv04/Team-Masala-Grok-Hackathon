import type { TaskRecord } from "@/types/domain";
import { StatusBadge } from "@/components/ui/status-badge";

export function TaskCard({ task }: { task: TaskRecord }) {
  return (
    <article className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-100">{task.input.title}</h3>
        <StatusBadge value={task.status} />
      </div>
      <p className="text-xs text-zinc-400">{task.input.description}</p>
      <p className="mt-2 text-xs text-zinc-500">Requested by {task.input.requestedBy}</p>
    </article>
  );
}
