"use client"

import React from "react"
import {
  Check,
  AlertTriangle,
  Loader2,
  FileText,
  Search,
  Calculator,
  FileSpreadsheet,
  Layers,
} from "lucide-react"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { AgentStep } from "@/types/workbench"
import { cn } from "@/lib/utils"

interface AgentStepAccordionProps {
  steps: AgentStep[]
}

export function AgentStepAccordion({ steps }: AgentStepAccordionProps) {
  const getStatusIcon = (status: AgentStep["status"]) => {
    switch (status) {
      case "passed":
      case "repaired":
        return <Check className="size-3.5 text-emerald-500" />
      case "failed":
        return <AlertTriangle className="size-3.5 text-destructive" />
      case "running":
        return <Loader2 className="size-3.5 text-amber-500 animate-spin" />
      default:
        return <span className="size-2 rounded-full bg-muted-foreground/40" />
    }
  }

  const getStepIcon = (title: string) => {
    const t = title.toLowerCase()
    if (t.includes("read") || t.includes("scan")) return <FileText className="size-3.5 text-muted-foreground" />
    if (t.includes("sop") || t.includes("rule")) return <Search className="size-3.5 text-muted-foreground" />
    if (t.includes("calc") || t.includes("math") || t.includes("formula")) return <Calculator className="size-3.5 text-muted-foreground" />
    if (t.includes("document") || t.includes("word") || t.includes("excel")) return <FileSpreadsheet className="size-3.5 text-muted-foreground" />
    return <Layers className="size-3.5 text-muted-foreground" />
  }

  return (
    <div className="my-3 flex flex-col gap-2">
      <div className="flex items-center justify-between px-0.5">
        <span className="text-xs font-medium text-muted-foreground">
          Execution Steps ({steps.length})
        </span>
      </div>

      <Accordion multiple defaultValue={["step-1", "step-2", "step-3", "step-4", "step-5", "step-6"]} className="space-y-1.5 border-none">
        {steps.map((step, idx) => (
          <AccordionItem
            key={step.stepId}
            value={step.stepId}
            className="rounded-xl border border-border/70 bg-card/60 px-3.5 shadow-none transition-colors data-open:bg-card"
          >
            <AccordionTrigger className="py-2.5 hover:no-underline text-xs">
              <div className="flex flex-1 items-center justify-between pr-2 text-left">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="flex size-5 shrink-0 items-center justify-center">
                    {getStatusIcon(step.status)}
                  </div>
                  <span className="font-medium text-foreground text-xs truncate">
                    {step.title}
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {step.status === "repaired" && (
                    <span className="text-[10px] text-amber-500 font-medium bg-amber-500/10 px-1.5 py-0.5 rounded">
                      Auto-Corrected
                    </span>
                  )}
                  {step.durationMs ? (
                    <span className="text-[10px] text-muted-foreground">
                      {step.durationMs}ms
                    </span>
                  ) : null}
                </div>
              </div>
            </AccordionTrigger>

            <AccordionContent className="pt-1 pb-3 text-xs text-muted-foreground leading-relaxed">
              <div className="p-2.5 rounded-lg bg-muted/40 border border-border/40 text-foreground/90 font-normal">
                {step.description}
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  )
}
