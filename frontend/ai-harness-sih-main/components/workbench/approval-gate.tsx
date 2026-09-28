"use client"

import React, { useState } from "react"
import {
  AlertCircle,
  CheckCircle2,
  XCircle,
  RotateCcw,
  FileText,
  UserCheck,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useWorkbench } from "@/lib/workbench-context"
import { approvalGateConfig } from "@/lib/config"
import { cn } from "@/lib/utils"

export function ApprovalGate() {
  const { activeTask, handleApprove, handleReject, handleModify } = useWorkbench()
  const [approverName, setApproverName] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (!activeTask?.approvalData) return null
  const { approvalData, approvalStatus, currentState, approvalError } = activeTask

  const isApproved = approvalStatus === "approved" || currentState === "COMPLETE"
  const isRejected = approvalStatus === "rejected" || currentState === "FAILED"

  const submit = async (fn: () => Promise<void>) => {
    setIsSubmitting(true)
    try {
      await fn()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card className={cn(
      "my-4 rounded-xl border bg-card shadow-sm overflow-hidden transition-all",
      isApproved && "border-emerald-500/30 bg-emerald-500/5",
      isRejected && "border-destructive/30 bg-destructive/5",
      !isApproved && !isRejected && "border-amber-500/30 bg-card"
    )}>
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className={cn(
              "flex size-8 items-center justify-center rounded-lg border",
              isApproved && "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
              isRejected && "bg-destructive/10 text-destructive border-destructive/20",
              !isApproved && !isRejected && "bg-amber-500/10 text-amber-500 border-amber-500/20"
            )}>
              {isApproved ? (
                <CheckCircle2 className="size-4" />
              ) : isRejected ? (
                <XCircle className="size-4" />
              ) : (
                <AlertCircle className="size-4" />
              )}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {approvalGateConfig.title}
              </h3>
              <p className="text-xs text-muted-foreground">
                {approvalGateConfig.subtitle}
              </p>
            </div>
          </div>

          <Badge
            variant="outline"
            className={cn(
              "text-[11px] font-medium px-2.5 py-0.5 rounded-md",
              isApproved && "border-emerald-500/30 bg-emerald-500/10 text-emerald-500",
              isRejected && "border-destructive/30 bg-destructive/10 text-destructive",
              !isApproved && !isRejected && "border-amber-500/30 bg-amber-500/10 text-amber-500"
            )}
          >
            {isApproved ? "Approved" : isRejected ? "Declined" : "Action Required"}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="p-4 pt-1 space-y-3">
        {/*
          A decision that the backend refused. The task state is deliberately left
          untouched in this case, so this panel is the only thing telling the operator
          the sign-off did NOT happen. See Frontend-fix.md item 1.8.
        */}
        {approvalError && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/5 p-3 text-xs text-foreground"
          >
            <AlertCircle className="size-4 text-red-500 shrink-0 mt-px" />
            <div className="space-y-0.5">
              <p className="font-semibold">The decision was not recorded.</p>
              <p className="text-muted-foreground">{approvalError}</p>
            </div>
          </div>
        )}

        {/* Recommendation Statement — only what the backend actually sent */}
        {(approvalData.recommendation || approvalData.rationale) && (
          <div className="rounded-lg border border-border/80 bg-background/60 p-3">
            <span className="text-[11px] font-medium uppercase text-muted-foreground tracking-wider">
              Recommendation
            </span>
            {approvalData.recommendation && (
              <p className="mt-1 text-sm font-semibold text-foreground leading-snug">
                {approvalData.recommendation}
              </p>
            )}
            {approvalData.rationale && (
              <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed">
                {approvalData.rationale}
              </p>
            )}
          </div>
        )}

        {/*
          Metrics grid. The backend `approval_requested` event carries none of these,
          so each cell renders only when a producer actually supplied a value.
          See Frontend-fix.md item 1.4.
        */}
        {(approvalData.measuredValue ||
          approvalData.thresholdValue ||
          approvalData.standardRef ||
          approvalData.complianceStatus) && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {approvalData.measuredValue && (
              <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
                <span className="text-[11px] text-muted-foreground">Measured Thickness</span>
                <p className="mt-0.5 text-base font-bold text-destructive">{approvalData.measuredValue}</p>
              </div>
            )}
            {approvalData.thresholdValue && (
              <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
                <span className="text-[11px] text-muted-foreground">Safe Limit</span>
                <p className="mt-0.5 text-base font-bold text-foreground">{approvalData.thresholdValue}</p>
              </div>
            )}
            {approvalData.standardRef && (
              <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
                <span className="text-[11px] text-muted-foreground">Standard</span>
                <p className="mt-0.5 text-xs font-medium text-foreground truncate">{approvalData.standardRef}</p>
              </div>
            )}
          </div>
        )}

        {/* Awaiting sign-off */}
        {approvalData.deliverablesPending && approvalData.deliverablesPending.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground pt-1">
            <span className="text-[11px]">Awaiting sign-off:</span>
            {approvalData.deliverablesPending.map((doc) => (
              <span key={doc} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-secondary text-foreground text-[11px]">
                <FileText className="size-3 text-muted-foreground" />
                {doc}
              </span>
            ))}
          </div>
        )}
      </CardContent>

      <CardFooter className="flex flex-wrap items-center justify-between gap-2.5 border-t border-border/60 bg-muted/30 p-3">
        {isApproved || isRejected ? (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <UserCheck className="size-3.5" />
            <span>
              {approvalStatus === "approved" ? "Approved" : "Rejected"} by{" "}
              {activeTask.approvedBy ?? "an unrecorded approver"}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <UserCheck className="size-3.5 shrink-0" />
            {/* There is no authentication in this build (AGENTS.md G7), so the
                approver is free text. It is no longer hardcoded to a job title —
                a named decision is recorded against whoever actually signs. */}
            <Input
              value={approverName}
              onChange={(e) => setApproverName(e.target.value)}
              placeholder="Your name"
              aria-label="Approver name"
              disabled={isSubmitting}
              className="h-7 w-44 text-xs"
            />
          </div>
        )}

        {!isApproved && !isRejected ? (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void submit(handleModify)}
              disabled={isSubmitting}
              className="gap-1.5 text-xs h-8 px-2.5 cursor-pointer"
            >
              <RotateCcw className="size-3.5" />
              <span>Adjust</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                void submit(() => handleReject(approverName.trim() || "unnamed approver"))
              }
              disabled={isSubmitting}
              className="gap-1.5 text-xs text-destructive hover:bg-destructive/10 h-8 px-2.5 cursor-pointer"
            >
              <XCircle className="size-3.5" />
              <span>Decline</span>
            </Button>
            <Button
              size="sm"
              onClick={() =>
                void submit(() => handleApprove(approverName.trim() || "unnamed approver"))
              }
              disabled={isSubmitting}
              className="gap-1.5 bg-foreground text-background hover:bg-foreground/90 text-xs font-semibold h-8 px-3.5 shadow-none cursor-pointer"
            >
              <CheckCircle2 className="size-3.5" />
              <span>Approve &amp; Sign</span>
            </Button>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">
            Sign-off recorded at {new Date().toLocaleTimeString()}
          </div>
        )}
      </CardFooter>
    </Card>
  )
}
