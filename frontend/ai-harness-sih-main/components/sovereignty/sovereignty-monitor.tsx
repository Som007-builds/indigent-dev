"use client"

import React from "react"
import { ShieldCheck, Sparkles, Server, AlertTriangle } from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useWorkbench } from "@/lib/workbench-context"
import { branding, sovereigntyConfig } from "@/lib/config"
import { cn } from "@/lib/utils"

export function SovereigntyMonitor() {
  const { sovereignty, refreshSovereignty, activeTask, isBackendConnected, activeModelId } =
    useWorkbench()

  /**
   * Three states, not two. Until the backend has actually answered, sovereignty is
   * UNKNOWN — which is neither "air-gapped" nor "violated". The previous code
   * collapsed this into a binary and, seeded from mock data, showed a green pulsing
   * AIR-GAPPED badge before any request had been made. See Frontend-fix.md item 1.7.
   */
  const isKnown = sovereignty.statusKnown
  const isAirGapped = isKnown && (sovereignty.isAirGapped || sovereignty.statusText === "AIR-GAPPED")
  const isViolated = isKnown && !isAirGapped
  // Counters are "not reported" while unknown — rendering them as 0 asserts zero egress.
  const externalCalls = isKnown ? (sovereignty.externalApiCalls ?? 0) : null
  const blockedAttempts = isKnown ? (sovereignty.deniedConnectionAttempts ?? 0) : null

  const modelLabel = activeTask?.routing?.modelName
    ? activeTask.routing.modelName.split("(")[0].trim()
    : activeModelId
    ? activeModelId.includes("/")
      ? activeModelId.split("/")[1]
      : activeModelId
    : null

  return (
    <header className="sticky top-0 z-40 flex h-13 w-full items-center justify-between border-b border-border bg-card/80 px-4 md:px-6 backdrop-blur-md">
      {/* Left: Clean Brand & Model Indicator */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex size-7 items-center justify-center rounded-lg bg-foreground text-background font-bold shadow-sm">
            <Sparkles className="size-4" />
          </div>
          <span className="text-sm font-semibold tracking-tight text-foreground">
            {branding.logoText}
          </span>
        </div>

        <div className="h-3.5 w-px bg-border" />

        {/* Model Badge — only names a model once one has actually been reported */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted/50 px-2.5 py-1 rounded-md border border-border/60">
          <span
            className={cn(
              "size-1.5 rounded-full",
              modelLabel ? "bg-emerald-500 animate-pulse" : "bg-neutral-600"
            )}
          />
          <span className="font-medium text-foreground">{modelLabel ?? "No model"}</span>
        </div>

        {/* Live Backend Connection Chip */}
        <div className="hidden lg:flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-full border">
          <Server className="size-3 text-muted-foreground" />
          {isBackendConnected ? (
            <span className="flex items-center gap-1 text-emerald-500 font-medium">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              <span>{branding.connectedStatus}</span>
            </span>
          ) : (
            <span className="flex items-center gap-1 text-amber-500 font-medium">
              <span className="size-1.5 rounded-full bg-amber-500" />
              <span>{branding.offlineStatus}</span>
            </span>
          )}
        </div>
      </div>

      {/* Right: Air-Gap Telemetry & Shield Test */}
      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-3 text-xs text-muted-foreground sm:flex">
          {/* Sovereignty Pill — AIR-GAPPED / VIOLATED / UNKNOWN */}
          <span
            className="flex items-center gap-1.5"
            title={
              isKnown
                ? sovereignty.statusText
                : "The backend has not reported sovereignty telemetry. This is unknown, not verified."
            }
          >
            <span
              className={cn(
                "size-2 rounded-full",
                isAirGapped
                  ? "bg-emerald-500 animate-pulse"
                  : isViolated
                  ? "bg-destructive animate-pulse"
                  : "bg-amber-500"
              )}
            />
            <span
              className={cn(
                "font-semibold",
                isViolated ? "text-destructive" : isAirGapped ? "text-foreground" : "text-amber-500"
              )}
            >
              {isAirGapped
                ? sovereigntyConfig.statusAirGapped
                : isViolated
                ? sovereigntyConfig.statusViolated
                : "Status Unknown"}
            </span>
          </span>

          <span className="text-border">|</span>

          {/* Egress Calls Telemetry */}
          <div className="flex items-center gap-1">
            <span className="font-mono text-foreground font-medium">
              {externalCalls ?? "—"}
            </span>
            <span>{sovereigntyConfig.labels.externalApiCalls.toLowerCase()}</span>
          </div>

          <span className="text-border">|</span>

          {/* Blocked Packets Telemetry */}
          <div className="flex items-center gap-1">
            <span className="font-mono text-foreground font-medium">
              {blockedAttempts ?? "—"}
            </span>
            <span>{sovereigntyConfig.labels.deniedAttempts.toLowerCase()}</span>
          </div>

          {/* Mode + provider, straight from the wire — never a default.
              `inferenceMode` is the value of the X-Inference-Mode header the backend
              sets on every response (app/main.py:116), so it needs no corroboration. */}
          {isKnown && (sovereignty.provider || sovereignty.inferenceMode) && (
            <>
              <span className="text-border">|</span>
              <span
                className="text-[11px]"
                title={
                  sovereignty.modeConflict
                    ? `Inconsistent backend: ${sovereignty.modeConflict}`
                    : "Inference mode as reported by the X-Inference-Mode response header"
                }
              >
                {sovereignty.inferenceMode ?? "unknown mode"}
                {sovereignty.provider ? ` · ${sovereignty.provider}` : ""}
              </span>
            </>
          )}

          {/* The backend asserts header/snapshot agreement in
              tests/integration/test_inference_mode_reporting.py. A conflict means we
              are reading an inconsistent backend — never paper over it. */}
          {sovereignty.modeConflict && (
            <>
              <span className="text-border">|</span>
              <span
                className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-500"
                title={`Mode disagreement: ${sovereignty.modeConflict}`}
              >
                <AlertTriangle className="size-3" />
                Mode mismatch
              </span>
            </>
          )}
        </div>

        <TooltipProvider delay={150}>
          <Tooltip>
            <TooltipTrigger
              onClick={() => void refreshSovereignty()}
              disabled={!isBackendConnected}
              className="inline-flex items-center gap-1.5 h-8 px-3 text-xs font-medium rounded-lg text-foreground hover:bg-muted border border-border transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ShieldCheck
                className={cn("size-3.5", isViolated ? "text-destructive" : "text-emerald-500")}
              />
              <span>Test Shield</span>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-xs max-w-xs p-2.5 space-y-1">
              <p className="font-medium text-foreground">Egress Denial Verification</p>
              {isBackendConnected ? (
                <>
                  <p className="text-muted-foreground">
                    Re-reads <code className="font-mono">/api/monitoring/sovereignty</code>. The
                    denial counters shown are those the backend has actually recorded.
                  </p>
                  <p className="text-muted-foreground">
                    Enforcement is the host-level guard in{" "}
                    <code className="font-mono">app/net/egress_guard.py</code>, which refuses
                    outbound connections and logs <code className="font-mono">EGRESS_DENIED</code>.
                    The backend exposes no endpoint that initiates a test connection, so this
                    button cannot and does not generate one.
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">
                  Backend unreachable — no sovereignty telemetry is available to verify.
                </p>
              )}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </header>
  )
}
