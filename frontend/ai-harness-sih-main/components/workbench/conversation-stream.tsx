"use client"

import React, { useState, useRef } from "react"
import {
  ArrowUp,
  Paperclip,
  Sparkles,
  FileText,
  X,
  Loader2,
  FileCheck,
  Cpu,
  ArrowRight,
  AlertTriangle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card } from "@/components/ui/card"
import { useWorkbench } from "@/lib/workbench-context"
import { RoutingReceiptBadge } from "./routing-receipt-badge"
import { AgentStepAccordion } from "./agent-step-accordion"
import { ApprovalGate } from "./approval-gate"
import { workbenchConfig, project } from "@/lib/config"

export function ConversationStream() {
  const { activeTask, submitMessage, isExecuting } = useWorkbench()
  const [inputVal, setInputVal] = useState("")
  const [attachedFiles, setAttachedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = async (customPrompt?: string) => {
    const textToSend = customPrompt !== undefined ? customPrompt : inputVal
    if ((!textToSend.trim() && attachedFiles.length === 0) || isExecuting) return
    const message = textToSend.trim() || (attachedFiles.length > 0 ? `Inspect attached file: ${attachedFiles[0].name}` : "")
    const filesToSend = [...attachedFiles]
    setInputVal("")
    setAttachedFiles([])
    await submitMessage(message, filesToSend)
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files)
      setAttachedFiles((prev) => [...prev, ...filesArray])
    }
  }

  const removeAttachedFile = (idx: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  const getScenarioAttachedFile = () => {
    if (attachedFiles.length > 0) {
      return {
        name: attachedFiles[0].name,
        size: `${(attachedFiles[0].size / 1024).toFixed(1)} KB`,
        type: attachedFiles[0].type || "Document",
      }
    }
    if (activeTask?.artifacts && activeTask.artifacts.length > 0) {
      const first = activeTask.artifacts[0]
      return { name: first.filename, size: first.fileSizeFormatted, type: first.fileType }
    }
    return null
  }

  const attachedFile = getScenarioAttachedFile()

  return (
    <div className="flex flex-1 flex-col h-full overflow-hidden bg-background">
      {/* Hidden file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        multiple
      />

      {/* Scrollable Conversation Thread / Welcome View */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {!activeTask ? (
            /* Welcome / Empty State with Quick Starters */
            <div className="py-8 md:py-14 space-y-8">
              <div className="text-center space-y-2">
                <div className="inline-flex size-12 items-center justify-center rounded-2xl bg-foreground text-background font-bold shadow-md mb-2">
                  <Sparkles className="size-6" />
                </div>
                <h1 className="text-xl md:text-2xl font-bold tracking-tight text-foreground">
                  {workbenchConfig.welcomeTitle}
                </h1>
                <p className="text-xs md:text-sm text-muted-foreground max-w-lg mx-auto leading-relaxed">
                  {workbenchConfig.welcomeSubtitle}
                </p>
              </div>

              {/* Quick Actions Grid */}
              <div className="space-y-2.5">
                <div className="text-[11px] font-medium text-muted-foreground px-1 uppercase tracking-wider">
                  {workbenchConfig.quickStartersTitle}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {workbenchConfig.quickStarters.map((starter, idx) => (
                    <Card
                      key={idx}
                      onClick={() => handleSend(starter.prompt)}
                      className="group p-4 border-border/80 bg-card/60 hover:bg-card hover:border-foreground/30 transition-all cursor-pointer shadow-none flex flex-col justify-between"
                    >
                      <div className="space-y-1">
                        <div className="text-xs font-semibold text-foreground group-hover:text-emerald-500 transition-colors flex items-center justify-between">
                          <span>{starter.title}</span>
                          <ArrowRight className="size-3 text-muted-foreground group-hover:text-emerald-500 group-hover:translate-x-0.5 transition-transform" />
                        </div>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                          {starter.description}
                        </p>
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Active Task Conversation Thread */
            <>
              {/* User Message Bubble */}
              <div className="flex items-start gap-3.5 justify-end">
                <div className="max-w-xl space-y-2">
                  <div className="rounded-2xl bg-secondary px-4 py-3 text-sm text-foreground shadow-sm">
                    <p className="leading-relaxed">
                      {activeTask.userPrompt}
                    </p>

                    {attachedFile && (
                      <div className="mt-2.5 flex items-center gap-2 pt-2 border-t border-border/40 text-xs text-muted-foreground">
                        <FileText className="size-3.5 text-foreground shrink-0" />
                        <span className="font-medium text-foreground truncate">{attachedFile.name}</span>
                        <span className="text-[11px]">({attachedFile.size})</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* AI Response Stream */}
              <div className="flex items-start gap-3.5">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground text-background font-bold mt-0.5 shadow-sm">
                  <Sparkles className="size-3.5" />
                </div>

                <div className="flex-1 min-w-0 space-y-3">
                  {/* Routing Receipt Badge */}
                  {activeTask.routing && <RoutingReceiptBadge routing={activeTask.routing} />}

                  {/* Agent Step Progression Accordion */}
                  <AgentStepAccordion steps={activeTask.steps || []} />

                  {/* Human-in-the-Loop Safety Approval Gate */}
                  {activeTask.requiresApproval && <ApprovalGate />}

                  {/* Verified AI Response Text Card */}
                  {activeTask.finalResult && (
                    <div className="rounded-2xl border border-border/80 bg-card p-4 md:p-5 text-sm text-foreground shadow-sm space-y-3">
                      <div className="flex items-center justify-between pb-2 border-b border-border/40">
                        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                          <Sparkles className="size-3.5 text-emerald-500" />
                          <span>{workbenchConfig.responseCardTitle || "Assistant Response"}</span>
                        </div>
                        {activeTask.currentState === "COMPLETE" && (
                          <span className="text-[10px] font-medium text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                            Verified
                          </span>
                        )}
                      </div>
                      <div className="text-xs md:text-sm text-foreground/95 leading-relaxed whitespace-pre-wrap font-normal selection:bg-foreground selection:text-background">
                        {activeTask.finalResult}
                      </div>
                    </div>
                  )}

                  {/* In-progress indicator if executing and not yet completed */}
                  {isExecuting && !activeTask.finalResult && !activeTask.requiresApproval && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground py-2 px-1">
                      <Loader2 className="size-3.5 animate-spin text-amber-500" />
                      <span>{workbenchConfig.generatingResponse || "Processing request & generating response..."}</span>
                    </div>
                  )}

                  {/*
                    Live updates were interrupted. Without this the panel simply stops
                    growing while the task is still running, which reads as "finished".
                    Deliberately worded for a plant manager, not an engineer: no stream,
                    no SSE, no event id. The task was NOT failed -- the backend keeps
                    running it (G11) -- so this must not be styled as an error.
                  */}
                  {activeTask.streamError && (
                    <div className="flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-foreground shadow-sm">
                      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" />
                      <div className="min-w-0 space-y-1">
                        <p className="text-sm font-medium text-foreground">
                          Live updates were interrupted
                        </p>
                        <p className="text-xs leading-relaxed text-muted-foreground">
                          This work is still running on the secure system, but updates have
                          stopped reaching this page. Reconnecting to pick up where it left
                          off.
                        </p>
                        <p className="break-words text-[11px] leading-relaxed text-muted-foreground/80">
                          {activeTask.streamError}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Input Console */}
      <div className="p-4 bg-background/80 backdrop-blur shrink-0 border-t border-border/40">
        <div className="max-w-3xl mx-auto">
          {/* Attached Files Preview Pills */}
          {attachedFiles.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {attachedFiles.map((file, idx) => (
                <div
                  key={`${file.name}-${idx}`}
                  className="flex items-center gap-1.5 bg-secondary px-2.5 py-1 rounded-md text-xs text-foreground border border-border"
                >
                  <FileText className="size-3.5 text-muted-foreground" />
                  <span className="truncate max-w-[180px]">{file.name}</span>
                  <button
                    onClick={() => removeAttachedFile(idx)}
                    className="text-muted-foreground hover:text-foreground ml-1 cursor-pointer"
                  >
                    <X className="size-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="relative rounded-2xl border border-border bg-card shadow-sm transition-all focus-within:border-foreground/30 focus-within:ring-1 focus-within:ring-foreground/20">
            <Textarea
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={workbenchConfig.inputPlaceholder}
              className="min-h-[52px] max-h-32 resize-none border-0 bg-transparent px-4 pt-3 pb-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:ring-0 shadow-none"
              rows={1}
              disabled={isExecuting}
            />

            <div className="flex items-center justify-between px-3 pb-2.5 pt-0.5">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={isExecuting}
                className="size-8 p-0 text-muted-foreground hover:text-foreground rounded-lg cursor-pointer"
                title="Attach document or scan"
              >
                <Paperclip className="size-4" />
              </Button>

              <Button
                size="sm"
                onClick={() => handleSend()}
                disabled={(!inputVal.trim() && attachedFiles.length === 0) || isExecuting}
                className="size-8 p-0 rounded-full bg-foreground text-background hover:bg-foreground/90 disabled:opacity-30 disabled:hover:bg-foreground transition-opacity cursor-pointer"
                title="Send message"
              >
                {isExecuting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ArrowUp className="size-4" />
                )}
              </Button>
            </div>
          </div>

          <div className="mt-2 text-center">
            <span className="text-[11px] text-muted-foreground">
              {project.name} operates 100% on-premise without external network access.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
