import { z } from "zod";

export const taskStatusSchema = z.enum([
  "queued",
  "running",
  "waiting_approval",
  "succeeded",
  "failed",
]);

export const taskInputSchema = z.object({
  title: z.string().min(3).max(120),
  description: z.string().min(5).max(2000),
  requestedBy: z.string().min(2).max(80),
  roleHints: z.array(z.string().min(1)).max(8).optional(),
});

export const taskRecordSchema = z.object({
  id: z.string().min(1),
  input: taskInputSchema,
  status: taskStatusSchema,
  workflowId: z.string().min(1),
  result: z.string().optional(),
  error: z.string().optional(),
  createdAt: z.string().min(1),
  updatedAt: z.string().min(1),
});

export type TaskInputDto = z.infer<typeof taskInputSchema>;
