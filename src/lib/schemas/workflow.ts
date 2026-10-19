import { z } from "zod";

export const workflowStatusSchema = z.enum([
  "pending",
  "running",
  "succeeded",
  "failed",
]);

export const agentMessageSchema = z.object({
  id: z.string(),
  role: z.enum(["system", "agent", "tool", "human"]),
  agentRole: z.string().optional(),
  content: z.string(),
  createdAt: z.string(),
});

export const workflowRecordSchema = z.object({
  id: z.string(),
  taskId: z.string(),
  name: z.string(),
  status: workflowStatusSchema,
  currentStep: z.string(),
  steps: z.array(z.string()),
  timeline: z.array(agentMessageSchema),
  updatedAt: z.string(),
});
