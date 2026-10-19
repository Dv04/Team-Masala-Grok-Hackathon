import type { TaskRecord, WorkflowRecord } from "@/types/domain";
import { StatusBadge } from "@/components/ui/status-badge";

export function ResultsPanel({
  tasks,
  workflows,
}: {
  tasks: TaskRecord[];
  workflows: WorkflowRecord[];
}) {
  const latestTask = tasks[0];
  const latestWorkflow = workflows[0];

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
      <h2 className="mb-3 text-sm font-semibold text-zinc-100">Results panel</h2>
      {!latestTask ? (
        <p className="text-sm text-zinc-500">Submit a task to view results.</p>
      ) : (
        <div className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <p className="text-zinc-200">{latestTask.input.title}</p>
            <StatusBadge value={latestTask.status} />
          </div>
          <p className="text-xs text-zinc-400">{latestTask.result ?? latestTask.error ?? "In progress..."}</p>
          {latestWorkflow ? (
            <p className="text-[11px] text-zinc-500">
              Workflow: {latestWorkflow.name} · step: {latestWorkflow.currentStep}
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
