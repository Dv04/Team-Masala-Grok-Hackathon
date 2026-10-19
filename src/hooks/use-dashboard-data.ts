"use client";

import { useCallback, useEffect, useState } from "react";
import type { TaskRecord, WorkflowRecord } from "@/types/domain";
import { createTaskResponseSchema, tasksResponseSchema, workflowsResponseSchema } from "@/lib/schemas/api";

export function useDashboardData() {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [taskRes, workflowRes] = await Promise.all([
        fetch("/api/tasks", { cache: "no-store" }),
        fetch("/api/workflows", { cache: "no-store" }),
      ]);

      const tasksPayload = tasksResponseSchema.parse(await taskRes.json());
      const workflowsPayload = workflowsResponseSchema.parse(await workflowRes.json());

      setTasks(tasksPayload.tasks);
      setWorkflows(workflowsPayload.workflows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const bootstrap = setTimeout(() => {
      void refresh();
    }, 0);
    const interval = setInterval(() => {
      void refresh();
    }, 1500);
    return () => {
      clearTimeout(bootstrap);
      clearInterval(interval);
    };
  }, [refresh]);

  const submitTask = useCallback(
    async (input: { title: string; description: string; requestedBy: string }) => {
      const response = await fetch("/api/tasks", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(input),
      });

      const payload = createTaskResponseSchema.parse(await response.json());
      setTasks((previous) => [payload.task, ...previous]);
      return payload.task;
    },
    [],
  );

  return {
    tasks,
    workflows,
    loading,
    error,
    refresh,
    submitTask,
  };
}
