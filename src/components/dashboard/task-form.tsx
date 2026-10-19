"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

interface TaskFormProps {
  onSubmit: (input: {
    title: string;
    description: string;
    requestedBy: string;
  }) => Promise<void>;
}

export function TaskForm({ onSubmit }: TaskFormProps) {
  const [title, setTitle] = useState("Mock challenge task");
  const [description, setDescription] = useState(
    "Create a local mock task to verify end-to-end starter workflow execution.",
  );
  const [requestedBy, setRequestedBy] = useState("Developer 1");
  const [submitting, setSubmitting] = useState(false);

  return (
    <form
      className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/70 p-4"
      onSubmit={async (event) => {
        event.preventDefault();
        setSubmitting(true);
        try {
          await onSubmit({ title, description, requestedBy });
        } finally {
          setSubmitting(false);
        }
      }}
    >
      <div>
        <p className="mb-2 text-sm font-medium text-zinc-200">Submit test task</p>
        <p className="text-xs text-zinc-500">This runs the clearly-labeled LOCAL MOCK workflow only.</p>
      </div>

      <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Task title" />
      <Textarea
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        rows={3}
        placeholder="Task description"
      />
      <Input
        value={requestedBy}
        onChange={(event) => setRequestedBy(event.target.value)}
        placeholder="Requested by"
      />

      <Button type="submit" disabled={submitting} className="w-full">
        {submitting ? "Submitting..." : "Run LOCAL MOCK Task"}
      </Button>
    </form>
  );
}
