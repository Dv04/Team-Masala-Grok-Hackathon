import { z } from "zod";
import { taskRecordSchema, taskInputSchema } from "@/lib/schemas/task";
import { workflowRecordSchema } from "@/lib/schemas/workflow";

export const errorResponseSchema = z.object({
  ok: z.literal(false),
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().optional(),
  }),
});

export const healthResponseSchema = z.object({
  ok: z.literal(true),
  service: z.literal("grokbot-hackathon-starter"),
  mode: z.enum(["mock", "xai"]),
  timestamp: z.string(),
});

export const agentsResponseSchema = z.object({
  ok: z.literal(true),
  agents: z.array(
    z.object({
      id: z.string(),
      role: z.string(),
      description: z.string(),
      provider: z.string(),
    }),
  ),
});

export const tasksResponseSchema = z.object({
  ok: z.literal(true),
  tasks: z.array(taskRecordSchema),
});

export const createTaskRequestSchema = taskInputSchema;

export const createTaskResponseSchema = z.object({
  ok: z.literal(true),
  task: taskRecordSchema,
});

export const workflowsResponseSchema = z.object({
  ok: z.literal(true),
  workflows: z.array(workflowRecordSchema),
});
