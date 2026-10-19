import type { TaskStatus, WorkflowStatus } from "@/types/domain";

const palette: Record<string, string> = {
  queued: "bg-zinc-700 text-zinc-200",
  running: "bg-blue-500/20 text-blue-200",
  waiting_approval: "bg-amber-500/20 text-amber-200",
  succeeded: "bg-emerald-500/20 text-emerald-200",
  failed: "bg-rose-500/20 text-rose-200",
  pending: "bg-zinc-700 text-zinc-200",
};

export function StatusBadge({ value }: { value: TaskStatus | WorkflowStatus }) {
  return (
    <span className={`rounded-full px-2 py-1 text-xs font-medium ${palette[value] ?? palette.pending}`}>
      {value}
    </span>
  );
}
