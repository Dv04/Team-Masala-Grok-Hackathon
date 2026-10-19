"use client";

import { useEffect, useState } from "react";
import { TaskForm } from "@/components/dashboard/task-form";
import { TaskCard } from "@/components/dashboard/task-card";
import { ActivityTimeline } from "@/components/dashboard/activity-timeline";
import { ResultsPanel } from "@/components/dashboard/results-panel";
import { ErrorState } from "@/components/dashboard/error-state";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingIndicator } from "@/components/ui/loading-indicator";
import { AgentGrid } from "@/components/agents/agent-grid";
import { WorkflowCard } from "@/components/workflows/workflow-card";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useToast } from "@/components/ui/toast";

interface AgentSummary {
  id: string;
  role: string;
  description: string;
  provider: string;
}

export function DashboardShell() {
  const { tasks, workflows, loading, error, submitTask, refresh } = useDashboardData();
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const { push } = useToast();

  useEffect(() => {
    const loadAgents = async () => {
      const response = await fetch("/api/agents", { cache: "no-store" });
      const payload = await response.json();
      setAgents(payload.agents ?? []);
    };

    void loadAgents();
  }, []);

  return (
    <div className="space-y-4 p-4 lg:p-6">
      {loading ? <LoadingIndicator label="Loading dashboard" /> : null}
      {error ? <ErrorState error={error} /> : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <TaskForm
          onSubmit={async (input) => {
            try {
              await submitTask(input);
              push("LOCAL MOCK task submitted", "success");
              await refresh();
            } catch (submitError) {
              push(
                submitError instanceof Error
                  ? submitError.message
                  : "Failed to submit task",
                "error",
              );
            }
          }}
        />

        <ResultsPanel tasks={tasks} workflows={workflows} />
        <ActivityTimeline workflows={workflows} />
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-zinc-100">Recent tasks</h2>
        {tasks.length === 0 ? (
          <EmptyState
            title="No tasks yet"
            description="Submit a test task to run the LOCAL MOCK workflow end-to-end."
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </div>
        )}
      </section>

      <AgentGrid agents={agents} />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-zinc-100">Workflows</h2>
        {workflows.length === 0 ? (
          <EmptyState title="No workflows yet" description="Workflow records appear after first task execution." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {workflows.map((workflow) => (
              <WorkflowCard key={workflow.id} workflow={workflow} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
