"use client"

import React from "react"
import { ConversationStream } from "@/components/workbench/conversation-stream"
import { ContextPanel } from "@/components/context-panel/context-panel"

export default function WorkbenchPage() {
  return (
    <div className="flex h-full w-full overflow-hidden">
      <ConversationStream />
      <ContextPanel />
    </div>
  )
}
