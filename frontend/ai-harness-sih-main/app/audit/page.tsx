"use client"

import React, { useState, useEffect } from "react"
import {
  History,
  Download,
  Check,
  AlertTriangle,
  Shield,
  Loader2,
  FolderOpen,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useWorkbench } from "@/lib/workbench-context"
import { apiClient } from "@/lib/api-client"
import { auditConfig } from "@/lib/config"

/**
 * One row of `audit_log`, as returned by `GET /api/tasks/{id}/timeline` and
 * `GET /api/tasks/timeline/all`.
 *
 * The real columns are exactly those of the `audit_log` table (G10, and
 * `app/core/schema.sql:8-9`):
 *   id, task_id, ts, inference_mode, category, component, action, status, details
 *
 * There is **no `actor` column and no `seq` column** — `seq` belongs to
 * `task_events`, a different table. The previous version of this file invented an
 * `actor` (defaulting to the literal "Orchestrator") and keyed rows off `seq` with an
 * index fallback, so every row was attributed to a component that never existed.
 */
interface AuditRow {
  id: string
  timestamp: string
  /** `action` column — e.g. "task_created", "state_changed", "generate", "integrity check". */
  action: string
  /** `category` column — e.g. "TASK_CREATED", "POLICY_ALLOWED", "PROVIDER_CALL". */
  category: string
  /** `component` column — e.g. "runner", "inference", "artifacts", "sovereignty". */
  component: string
  /** `status` column — the backend emits ok | error | denied | info. */
  status: string
  /** `inference_mode` column — required NOT NULL, and previously never displayed. */
  inferenceMode: string
  details: string
}

/**
 * Render the `status` column exactly as recorded.
 *
 * `app/core/audit.py` defaults `status="info"`, and the call sites in
 * `app/core/taskrunner.py`, `app/core/artifacts.py`, `app/net/sovereignty.py` and
 * `app/agent/inference.py` pass `"ok"`, `"error"` or `"denied"`. The previous
 * component tested for `"blocked"`, which is never written, and relabelled the other
 * three as "Completed" / "Blocked" / "Pending" — so a genuine `denied` (emitted when a
 * model/provider violates the inference-mode policy) rendered as a green "Pending".
 *
 * An unrecognised value is shown verbatim in neutral styling rather than being
 * coerced into one of the known buckets.
 */
function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "error" || status === "denied"
      ? "text-destructive bg-destructive/10"
      : status === "ok"
      ? "text-emerald-500 bg-emerald-500/10"
      : "text-amber-500 bg-amber-500/10"
  const Icon =
    status === "error" || status === "denied"
      ? Shield
      : status === "ok"
      ? Check
      : AlertTriangle

  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md ${tone}`}
    >
      <Icon className="size-3" />
      <span>{status}</span>
    </span>
  )
}

/** The backend stores ISO-8601 UTC (G6). Keep the raw value if it will not parse. */
function formatTimestamp(ts: string): string {
  const parsed = new Date(ts)
  return Number.isNaN(parsed.getTime()) ? ts : parsed.toLocaleString()
}

export default function AuditPage() {
  const { activeTask, isBackendConnected } = useWorkbench()
  const [entries, setEntries] = useState<AuditRow[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [auditError, setAuditError] = useState<string | null>(null)

  const loadAuditLogs = async () => {
    setIsLoading(true)
    setAuditError(null)
    try {
      const res =
        activeTask?.taskId && !activeTask.taskId.startsWith("task-scenario-")
          ? await apiClient.getTimeline(activeTask.taskId)
          : await apiClient.getAllTimeline()

      if (res?.entries) {
        // Map the real columns only. Every previous fallback here ("Orchestrator",
        // "State Transition", `idx + 1000`) substituted a value the database does not
        // contain; `id` and `ts` are NOT NULL, so omitting the fallbacks is safe.
        const mapped: AuditRow[] = res.entries.map((item, idx) => ({
          id: String(item.id ?? `row-${idx}`),
          timestamp: item.ts,
          action: item.action,
          category: item.category,
          component: item.component,
          // The backend emits ok | error | denied | info. The old mapping tested for
          // "blocked", which is never written, so the red "Blocked" treatment was dead
          // code and both "denied" and "info" fell through to a green/amber "Pending".
          status: item.status,
          inferenceMode: item.inference_mode,
          details:
            typeof item.details === "object" && item.details !== null
              ? JSON.stringify(item.details)
              : String(item.details ?? ""),
        }))
        setEntries(mapped)
      } else {
        setEntries([])
      }
    } catch (err) {
      // Previously swallowed. An empty table and a "no records found" message are
      // indistinguishable from a genuinely empty ledger, so a backend failure looked
      // like a clean audit trail.
      setEntries([])
      setAuditError(err instanceof Error ? err.message : "Failed to load the audit log")
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadAuditLogs()
  }, [isBackendConnected, activeTask?.taskId])

  const handleExportJSONL = () => {
    const jsonlContent = entries.map((e) => JSON.stringify(e)).join("\n")
    const blob = new Blob([jsonlContent], { type: "application/x-jsonlines" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `audit_log_${activeTask?.taskId || "export"}.jsonl`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 pb-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <History className="size-4 text-muted-foreground" />
            <span>{auditConfig.title}</span>
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {auditConfig.subtitle}
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={handleExportJSONL}
          disabled={entries.length === 0}
          className="gap-1.5 text-xs font-medium rounded-lg cursor-pointer"
        >
          <Download className="size-3.5" />
          <span>{auditConfig.exportButton}</span>
        </Button>
      </div>

      {/* Audit Log Table */}
      <Card className="border-border/80 rounded-xl overflow-hidden shadow-none bg-card">
        {isLoading ? (
          <div className="py-12 flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
            <span>Loading audit records from SQLite ledger...</span>
          </div>
        ) : auditError ? (
          <div className="py-14 text-center space-y-2 px-6">
            <AlertTriangle className="size-6 text-destructive mx-auto" />
            <p className="text-xs font-medium text-foreground">
              The audit log could not be read
            </p>
            <p className="text-[11px] text-muted-foreground max-w-md mx-auto">
              {auditError}
            </p>
            <p className="text-[11px] text-muted-foreground max-w-md mx-auto">
              This is <strong>not</strong> an empty audit trail — the ledger could not be
              queried, so its contents are unknown.
            </p>
          </div>
        ) : entries.length === 0 ? (
          <div className="py-16 text-center space-y-3">
            <div className="inline-flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <FolderOpen className="size-5" />
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-foreground">
                The audit ledger is empty
              </p>
              <p className="text-[11px] text-muted-foreground max-w-sm mx-auto">
                The backend was queried successfully and returned zero rows. Entries are
                appended as tasks execute, tool calls run, and policy decisions are made.
              </p>
            </div>
          </div>
        ) : (
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow>
                <TableHead className="text-xs font-medium text-muted-foreground">
                  {auditConfig.table.time}
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">
                  {auditConfig.table.action}
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">
                  {auditConfig.table.module}
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">
                  Category
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">
                  Mode
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">
                  {auditConfig.table.status}
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">
                  {auditConfig.table.details}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.id} className="hover:bg-muted/20">
                  <TableCell className="text-xs text-muted-foreground font-mono py-3 whitespace-nowrap">
                    {formatTimestamp(entry.timestamp)}
                  </TableCell>
                  <TableCell className="text-xs font-semibold text-foreground">
                    {entry.action}
                  </TableCell>
                  {/* The real `component` column: runner | inference | artifacts |
                      tasks | startup | sovereignty. */}
                  <TableCell className="text-xs text-muted-foreground">
                    {entry.component}
                  </TableCell>
                  {/* The real `category` column: TASK_CREATED, POLICY_ALLOWED,
                      PROVIDER_CALL, ARTIFACT_CREATED, EGRESS_DENIED, … */}
                  <TableCell className="text-xs text-muted-foreground font-mono text-[10px]">
                    {entry.category}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground font-mono text-[10px]">
                    {entry.inferenceMode}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={entry.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground leading-relaxed max-w-md truncate">
                    {entry.details}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  )
}
