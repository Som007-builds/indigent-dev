/**
 * One place that builds a `RoutingReceipt` from what the backend actually reported.
 *
 * ## Why this is shared
 *
 * Three call sites used to construct a receipt independently, and every one of them
 * invented a model when the backend had not sent one:
 *
 *   * `model_selected` event  -> `"groq-model"` / `"Groq Model"`
 *   * `loadTask` (task record) -> `task.model_used || "groq-model"`
 *   * `submitMessage`         -> the locally selected model, before any event arrived
 *
 * `model_used` is nullable (`app/core/schema.sql`, the `tasks` table) and is only
 * populated by a `model_selected` event, so on any task that never selected a model
 * the badge rendered the literal string **"groq-model"** — a Groq model, named as a
 * fact, inside a product whose entire premise is that it never calls Groq. G9 defines
 * `model_selected` as `{model_id, model_name, provider}`; it carries no residency
 * flag, yet all three sites asserted `isResident: true`.
 *
 * The governing rule is the same one used in items 1.6-1.13: never display a value
 * the backend did not send. So when the backend reports nothing, this says so.
 */

import { ModelRole, RoutingReceipt } from "@/types/workbench"

/**
 * Stands in for a model name the backend never reported.
 *
 * Module-private, not exported: the three builders below share it so the literal
 * cannot drift between them, but nothing outside needs to compare against it.
 */
const MODEL_NOT_REPORTED = "Not reported"

/** Stands in for the model, before the orchestrator has selected one. */
const MODEL_PENDING = "Awaiting selection"

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined
}

/**
 * From a `model_selected` event (`G9`: `{model_id, model_name, provider}`).
 *
 * `provider` was previously discarded; it is the most useful thing here, because in
 * an air-gapped product the provider *is* the sovereignty claim. It now appears in
 * the reason text when the backend sends it.
 */
export function routingFromModelSelected(data: Record<string, unknown>): RoutingReceipt {
  const modelId = text(data.model_id)
  const modelName = text(data.model_name)
  const provider = text(data.provider)

  const label = modelName ?? modelId ?? MODEL_NOT_REPORTED

  let reason: string
  if (!modelId && !modelName) {
    reason = "The orchestrator reported no model for this task."
  } else if (provider) {
    reason = `Selected via ${provider}`
  } else if (modelName && modelId && modelName !== modelId) {
    reason = modelId
  } else {
    reason = "Selected by the orchestrator"
  }

  return { modelId: modelId ?? label, modelName: label, role: "general", reason }
}

/**
 * From a persisted task record (`GET /api/tasks/{id}`).
 *
 * `model_used` is set only by `model_selected`; it is `null` for a task that failed
 * before selection, which is exactly when the old `"groq-model"` fallback fired.
 */
export function routingFromTaskRecord(task: {
  model_used?: string | null
  inference_mode: string
  task_type?: string | null
}): RoutingReceipt {
  const modelId = text(task.model_used)
  const role: ModelRole = task.task_type === "coding" ? "coding" : "reasoning"

  if (!modelId) {
    return {
      modelId: MODEL_NOT_REPORTED,
      modelName: MODEL_NOT_REPORTED,
      role,
      reason: `No model recorded; task ran in ${task.inference_mode} mode.`,
    }
  }

  return {
    modelId,
    modelName: modelId,
    role,
    reason: `Recorded model for a task in ${task.inference_mode} mode.`,
  }
}

/**
 * The optimistic receipt shown between submitting and the first stream event.
 *
 * The old version named the model from client state, which asserts something the
 * backend has not confirmed: the active model may not even be settable (item 2.4 —
 * `POST /api/models/active` returns 501 unless the registry implements it), and the
 * orchestrator is free to route elsewhere. This states the pending status instead,
 * and is replaced the moment a `model_selected` event arrives.
 */
export function pendingRouting(): RoutingReceipt {
  return {
    modelId: MODEL_PENDING,
    modelName: MODEL_PENDING,
    role: "general",
    reason: "Waiting for the orchestrator to report the selected model.",
  }
}
