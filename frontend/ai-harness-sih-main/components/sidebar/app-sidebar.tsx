"use client"

import React, { useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  MessageSquareText,
  FileText,
  BookOpen,
  Map,
  Sliders,
  History,
  Plus,
  Check,
  CheckCircle2,
  Clock,
  ChevronRight,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { useWorkbench } from "@/lib/workbench-context"
import { project, workbenchConfig } from "@/lib/config"
import { cn } from "@/lib/utils"

const navItems = [
  {
    href: "/",
    label: "Workspace",
    icon: MessageSquareText,
  },
  {
    href: "/documents",
    label: "Documents",
    icon: FileText,
  },
  {
    href: "/knowledge",
    label: "Guidelines",
    icon: BookOpen,
  },
  {
    href: "/pid-viewer",
    label: "Diagrams",
    icon: Map,
  },
  {
    href: "/models",
    label: "Models",
    icon: Sliders,
  },
  {
    href: "/audit",
    label: "Audit Log",
    icon: History,
  },
]

export function AppSidebar() {
  const pathname = usePathname()
  const {
    activeTask,
    resetTask,
    recentTasks,
    refreshRecentTasks,
    loadTask,
    submitMessage,
  } = useWorkbench()

  const [sidebarWidth, setSidebarWidth] = React.useState<number>(256)
  const [isResizing, setIsResizing] = React.useState<boolean>(false)

  useEffect(() => {
    refreshRecentTasks().catch(() => {})
  }, [refreshRecentTasks])

  const startResizing = React.useCallback((mouseDownEvent: React.MouseEvent) => {
    mouseDownEvent.preventDefault()
    setIsResizing(true)

    const startX = mouseDownEvent.clientX
    const startWidth = sidebarWidth

    const onMouseMove = (mouseMoveEvent: MouseEvent) => {
      const delta = mouseMoveEvent.clientX - startX
      const newWidth = Math.min(Math.max(200, startWidth + delta), 460)
      setSidebarWidth(newWidth)
    }

    const onMouseUp = () => {
      setIsResizing(false)
      window.removeEventListener("mousemove", onMouseMove)
      window.removeEventListener("mouseup", onMouseUp)
    }

    window.addEventListener("mousemove", onMouseMove)
    window.addEventListener("mouseup", onMouseUp)
  }, [sidebarWidth])

  return (
    <aside
      style={{ width: `${sidebarWidth}px` }}
      className={cn(
        "relative flex h-full flex-col border-r border-border bg-sidebar shrink-0 text-sidebar-foreground select-none transition-[width] duration-75",
        isResizing && "transition-none select-none"
      )}
    >
      {/* Top Action: New Chat / Task */}
      <div className="p-3 border-b border-border/60">
        <Button
          variant="outline"
          size="sm"
          onClick={resetTask}
          className="w-full justify-between h-9 px-3 rounded-lg border-border/80 bg-background/80 hover:bg-muted font-medium text-xs text-foreground shadow-none cursor-pointer"
        >
          <span className="flex items-center gap-2">
            <Plus className="size-4 text-muted-foreground" />
            <span>New Task</span>
          </span>
          <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border">Ctrl+N</span>
        </Button>
      </div>

      {/* Recent History / Live Tasks */}
      <div className="p-3 border-b border-border/60 max-h-56 overflow-y-auto">
        <div className="mb-2 px-1 text-[11px] font-medium text-muted-foreground flex items-center justify-between">
          <span>Recent Tasks</span>
          <span className="text-[10px] text-muted-foreground font-mono">{recentTasks.length}</span>
        </div>

        {recentTasks.length > 0 ? (
          <div className="flex flex-col gap-1">
            {recentTasks.map((t) => {
              const isSelected = activeTask?.taskId === t.task_id
              const promptTitle = t.user_request || "Industrial Task"
              return (
                <button
                  key={t.task_id}
                  onClick={() => loadTask(t.task_id)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors cursor-pointer group",
                    isSelected
                      ? "bg-secondary text-foreground font-medium"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  )}
                  title={promptTitle}
                >
                  <span className="truncate flex-1">{promptTitle}</span>
                  {t.current_state === "COMPLETE" ? (
                    <CheckCircle2 className="size-3 text-emerald-500 shrink-0 ml-1.5 opacity-70 group-hover:opacity-100" />
                  ) : (
                    <Clock className="size-3 text-amber-500 shrink-0 ml-1.5 opacity-70 group-hover:opacity-100" />
                  )}
                </button>
              )
            })}
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {workbenchConfig.quickStarters.map((sc, i) => (
              <button
                key={i}
                onClick={() => submitMessage(sc.prompt)}
                className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted/60 hover:text-foreground transition-colors cursor-pointer group"
                title={sc.description}
              >
                <span className="truncate flex-1">{sc.title}</span>
                <ChevronRight className="size-3 text-muted-foreground opacity-50 group-hover:opacity-100 shrink-0 ml-1" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Navigation Routes */}
      <div className="flex-1 overflow-y-auto p-3">
        <div className="mb-2 px-1 text-[11px] font-medium text-muted-foreground">
          Navigation
        </div>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href))
            const Icon = item.icon
            return (
              <Link key={item.href} href={item.href}>
                <Button
                  variant={isActive ? "secondary" : "ghost"}
                  size="sm"
                  className={cn(
                    "w-full justify-start gap-2.5 text-xs h-8 px-2.5 rounded-lg shadow-none",
                    isActive
                      ? "font-semibold text-foreground bg-secondary"
                      : "text-muted-foreground hover:text-foreground font-normal"
                  )}
                >
                  <Icon className={cn("size-4", isActive ? "text-foreground" : "text-muted-foreground")} />
                  <span>{item.label}</span>
                </Button>
              </Link>
            )
          })}
        </nav>
      </div>

      {/* Minimal Status Footer */}
      <div className="p-3 border-t border-border/60 text-xs text-muted-foreground">
        <div className="flex items-center justify-between px-1 py-0.5">
          <span className="text-[11px] font-medium text-muted-foreground">{project.name} {project.version}</span>
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            Local
          </span>
        </div>
      </div>

      {/* Resize Drag Handle */}
      <div
        onMouseDown={startResizing}
        onDoubleClick={() => setSidebarWidth(256)}
        title="Drag to resize sidebar (double click to reset)"
        className={cn(
          "absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-emerald-500/50 transition-colors z-50",
          isResizing && "bg-emerald-500 w-1.5"
        )}
      />
    </aside>
  )
}
