"use client"

import React from "react"
import {
  Check,
  AlertTriangle,
  Loader2,
} from "lucide-react"
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area"
import { useWorkbench } from "@/lib/workbench-context"
import { AgentStep } from "@/types/workbench"
import { cn } from "@/lib/utils"

export function ExecutionTimeline() {
  const { activeTask } = useWorkbench()
  const steps = activeTask?.steps || []
  const currentState = activeTask?.currentState || "READY"

  const renderStepStatusIcon = (step: AgentStep) => {
    switch (step.status) {
      case "passed":
      case "repaired":
        return <Check className="size-3 text-emerald-500 shrink-0" />
      case "failed":
        return <AlertTriangle className="size-3 text-destructive shrink-0" />
      case "running":
        return <Loader2 className="size-3 text-amber-500 animate-spin shrink-0" />
      default:
        return <span className="size-1.5 rounded-full bg-muted-foreground/30 shrink-0" />
    }
  }

  return (
    <footer className="sticky bottom-0 z-30 flex h-10 w-full items-center border-t border-border/70 bg-card/90 px-4 backdrop-blur text-xs">
      <div className="flex shrink-0 items-center gap-2 pr-3 border-r border-border/60">
        <span className="text-[11px] font-medium text-muted-foreground">
          Workflow
        </span>
        <span className="text-[11px] font-medium text-foreground">
          {currentState === "APPROVAL" ? "Awaiting Sign-off" : currentState === "COMPLETE" ? "Complete" : currentState === "READY" ? "Ready" : "Running"}
        </span>
      </div>

      {/* Stepper Scroll Container */}
      <ScrollArea className="flex-1 whitespace-nowrap px-3">
        <div className="flex items-center gap-2 py-1">
          {steps.length > 0 ? (
            steps.map((step, idx) => (
              <React.Fragment key={step.stepId}>
                <div
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] transition-colors",
                    step.status === "passed" && "text-foreground bg-muted/40",
                    step.status === "repaired" && "text-foreground bg-muted/40",
                    step.status === "failed" && "text-destructive bg-destructive/10",
                    step.status === "running" && "text-amber-500 bg-amber-500/10 font-medium",
                    step.status === "pending" && "text-muted-foreground"
                  )}
                >
                  {renderStepStatusIcon(step)}
                  <span className="truncate max-w-[160px]">{step.title}</span>
                </div>

                {idx < steps.length - 1 && (
                  <span className="text-muted-foreground/40 text-[10px]">›</span>
                )}
              </React.Fragment>
            ))
          ) : (
            <span className="text-[11px] text-muted-foreground">
              Air-Gapped Standby · Ready for prompt
            </span>
          )}
        </div>
        <ScrollBar orientation="horizontal" className="h-1" />
      </ScrollArea>

      <div className="hidden shrink-0 items-center gap-1.5 pl-3 border-l border-border/60 text-[11px] text-muted-foreground sm:flex">
        <span>Task ID: {activeTask?.taskId || "None"}</span>
      </div>
    </footer>
  )
}
