"use client"

import React from "react"
import { Sparkles, Cpu } from "lucide-react"
import { RoutingReceipt } from "@/types/workbench"

interface RoutingReceiptBadgeProps {
  routing: RoutingReceipt
}

export function RoutingReceiptBadge({ routing }: RoutingReceiptBadgeProps) {
  return (
    <div className="flex items-center gap-2 py-1 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-foreground font-medium">
        <Cpu className="size-3 text-muted-foreground" />
        <span>{routing.modelName.split("(")[0].trim()}</span>
      </span>
      <span className="text-muted-foreground text-[11px] truncate">
        {routing.reason}
      </span>
    </div>
  )
}
