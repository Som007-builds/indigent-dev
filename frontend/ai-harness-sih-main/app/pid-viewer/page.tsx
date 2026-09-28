"use client"

import React, { useState, useRef } from "react"
import {
  Map,
  Search,
  Download,
  Upload,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react"
import { PIDGraphViewer } from "@/components/pid/pid-graph-viewer"
import { pidDiagramsList } from "@/lib/pid-data"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { apiClient, ApiError } from "@/lib/api-client"
import { pidConfig } from "@/lib/config"
import { PIDGraph, PIDEdge, PIDNode } from "@/types/workbench"
import { cn } from "@/lib/utils"

/** Uploads are tagged with this prefix so fixture data is never confused with analysed output. */
const ANALYSED_PREFIX = "PID-UPLOAD-"

function isAnalysedUpload(graph: PIDGraph): boolean {
  return graph.drawingId.startsWith(ANALYSED_PREFIX)
}

/** Render only what the backend actually returned — never a plausible stand-in. */
function describeError(err: unknown): string {
  if (err instanceof ApiError) return `${err.code}: ${err.message}`
  if (err instanceof Error) return err.message
  return "Unknown error"
}

/** Node type as declared on the wire. The backend PIDGraph nodes are free-form dicts. */
function nodeType(node: PIDNode): string {
  const raw = node as unknown as Record<string, unknown>
  return String(raw.symbolType ?? raw.symbol_type ?? raw.type ?? "").toLowerCase()
}

/**
 * Count equipment strictly from node types the backend actually declared.
 * Returns undefined when no node carries a recognisable type field, so the caller
 * omits the panel rather than displaying invented counts.
 */
function countEquipment(nodes: PIDNode[]): PIDGraph["equipmentCount"] | undefined {
  let typed = 0
  let valves = 0
  let pumps = 0
  let vessels = 0
  let instruments = 0

  for (const node of nodes) {
    const t = nodeType(node)
    if (!t) continue
    typed++
    if (t.includes("valve")) valves++
    else if (t.includes("pump")) pumps++
    else if (
      t.includes("column") ||
      t.includes("vessel") ||
      t.includes("tank") ||
      t.includes("reactor") ||
      t.includes("drum") ||
      t.includes("furnace") ||
      t.includes("compressor")
    )
      vessels++
    else if (t.includes("instrument") || t.includes("transmitter")) instruments++
  }

  if (typed === 0) return undefined
  return { valves, pumps, vessels, instruments }
}

export default function PIDViewerPage() {
  const [diagrams, setDiagrams] = useState<PIDGraph[]>(pidDiagramsList)
  const [selectedDrawingId, setSelectedDrawingId] = useState<string>(pidDiagramsList[0].drawingId)
  const [selectedCategory, setSelectedCategory] = useState<string>("All")
  const [searchQuery, setSearchQuery] = useState<string>("")
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const activeGraph = diagrams.find((d) => d.drawingId === selectedDrawingId) || diagrams[0]
  const analysedCount = diagrams.filter(isAnalysedUpload).length

  const flash = (message: string | null) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setToastMessage(message)
    if (message) toastTimerRef.current = setTimeout(() => setToastMessage(null), 6000)
  }

  const categories = ["All", "Primary Separation", "Hydroprocessing", "Overhead System", "Engineering Standards"]

  const filteredDiagrams = diagrams.filter((d) => {
    const matchesCategory = selectedCategory === "All" || d.category === selectedCategory
    const matchesSearch =
      d.drawingTitle.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.drawingId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.description?.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesCategory && matchesSearch
  })

  const handleUploadDrawing = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setIsAnalyzing(true)
    setErrorMessage(null)
    flash(null)

    try {
      const res = await apiClient.analyzePID(file)
      const graphData = res.graph
      const nodes = (graphData.nodes ?? []) as unknown as PIDNode[]
      const edges = (graphData.edges ?? []) as unknown as PIDEdge[]

      // app/api/pid.py:38 sets graph.overlay_artifact_id, and artifact_ids[1] is the
      // same id. graph.overlay_image_path is a server filesystem path and is NOT
      // servable, so the overlay is addressed through its artifact id instead.
      const overlayArtifactId = graphData.overlay_artifact_id ?? res.artifact_ids?.[1]
      const equipmentCount = countEquipment(nodes)

      const newDiagram: PIDGraph = {
        drawingId: `${ANALYSED_PREFIX}${Date.now().toString().slice(-4)}`,
        drawingTitle: file.name.replace(/\.[^/.]+$/, ""),
        // standard / category / description are not in the backend PIDGraph payload.
        // They are left unset rather than filled with a plausible value.
        nodes,
        edges,
        ...(overlayArtifactId
          ? { overlayImageUrl: apiClient.getArtifactDownloadUrl(overlayArtifactId) }
          : {}),
        ...(graphData.narrative ? { flowNarrative: graphData.narrative } : {}),
        ...(equipmentCount ? { equipmentCount } : {}),
      }

      setDiagrams((prev) => [newDiagram, ...prev])
      setSelectedDrawingId(newDiagram.drawingId)
      flash(
        `Analysis complete: ${nodes.length} node(s), ${edges.length} edge(s) extracted.` +
          (overlayArtifactId ? "" : " No overlay image was returned.")
      )
    } catch (err) {
      // A failed analysis must never produce a graph. Report what the backend said.
      setErrorMessage(`P&ID analysis failed — ${describeError(err)}`)
    } finally {
      setIsAnalyzing(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleExportJSON = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(activeGraph, null, 2))
    const downloadAnchor = document.createElement("a")
    downloadAnchor.setAttribute("href", dataStr)
    downloadAnchor.setAttribute("download", `${activeGraph.drawingId}_graph.json`)
    document.body.appendChild(downloadAnchor)
    downloadAnchor.click()
    downloadAnchor.remove()
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 max-w-7xl mx-auto">
      {/* Toast */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg bg-card border border-border px-4 py-3 text-xs text-foreground shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-150">
          <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Error — a failed analysis must never render a graph */}
      {errorMessage && (
        <div
          role="alert"
          className="fixed bottom-6 right-6 z-50 flex items-start gap-2 max-w-lg rounded-lg bg-card border border-red-500/50 px-4 py-3 text-xs text-foreground shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-150"
        >
          <AlertCircle className="size-4 text-red-500 shrink-0 mt-px" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Hidden File Input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleUploadDrawing}
        accept="image/*,.pdf"
        className="hidden"
      />

      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 pb-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Map className="size-4 text-muted-foreground" />
            <span>{pidConfig.title}</span>
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {pidConfig.subtitle}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={isAnalyzing}
            className="gap-1.5 text-xs font-medium rounded-lg h-8 cursor-pointer"
          >
            {isAnalyzing ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Upload className="size-3.5" />
            )}
            <span>{pidConfig.uploadButton}</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleExportJSON}
            className="gap-1.5 text-xs font-medium rounded-lg h-8 cursor-pointer"
          >
            <Download className="size-3.5" />
            <span>{pidConfig.exportButton}</span>
          </Button>
        </div>
      </div>

      {/* Overview Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-3.5 bg-card border-border/80 rounded-xl shadow-none">
          <span className="text-[11px] text-muted-foreground">Available Diagrams</span>
          <p className="text-lg font-semibold text-foreground mt-0.5">{diagrams.length} Units</p>
          <span className="text-[11px] text-muted-foreground">
            {analysedCount} analysed · {diagrams.length - analysedCount} bundled fixtures
          </span>
        </Card>

        <Card className="p-3.5 bg-card border-border/80 rounded-xl shadow-none">
          <span className="text-[11px] text-muted-foreground">Current Unit Equipment</span>
          <p className="text-lg font-semibold text-foreground mt-0.5">{activeGraph.nodes.length} Items</p>
          <span className="text-[11px] text-muted-foreground">Tagged &amp; Bounded</span>
        </Card>

        <Card className="p-3.5 bg-card border-border/80 rounded-xl shadow-none">
          <span className="text-[11px] text-muted-foreground">Piping &amp; Loops</span>
          <p className="text-lg font-semibold text-foreground mt-0.5">{activeGraph.edges.length} Connections</p>
          <span className="text-[11px] text-muted-foreground">Process &amp; Signals</span>
        </Card>

        <Card className="p-3.5 bg-card border-border/80 rounded-xl shadow-none">
          <span className="text-[11px] text-muted-foreground">Drawing Standard</span>
          <p className="text-lg font-semibold text-foreground mt-0.5">
            {activeGraph.standard ?? "Not declared"}
          </p>
          <span
            className={cn(
              "text-[11px] font-medium",
              isAnalysedUpload(activeGraph)
                ? "text-muted-foreground"
                : "text-amber-500"
            )}
          >
            {isAnalysedUpload(activeGraph)
              ? "Backend returned no standard"
              : "Bundled fixture metadata — not verified"}
          </span>
        </Card>
      </div>

      {/* Category Filter Pills & Search */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={cn(
                "px-3 py-1 rounded-lg text-xs font-medium transition-colors border cursor-pointer",
                selectedCategory === cat
                  ? "bg-foreground text-background border-foreground font-semibold"
                  : "bg-background/60 text-muted-foreground border-border hover:bg-muted hover:text-foreground"
              )}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search plant diagrams..."
            className="pl-8 h-8 text-xs rounded-lg"
          />
        </div>
      </div>

      {/* Diagrams Grid Switcher Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {filteredDiagrams.map((d) => {
          const isSelected = selectedDrawingId === d.drawingId
          return (
            <Card
              key={d.drawingId}
              onClick={() => setSelectedDrawingId(d.drawingId)}
              className={cn(
                "p-3.5 rounded-xl cursor-pointer transition-all shadow-none border text-left",
                isSelected
                  ? "border-emerald-500/50 bg-card ring-1 ring-emerald-500/30"
                  : "border-border/80 bg-card/60 hover:border-border hover:bg-card"
              )}
            >
              <div className="flex items-center justify-between text-[11px] text-muted-foreground mb-1.5">
                <span className="font-mono">{d.drawingId}</span>
                <span className="bg-secondary px-1.5 py-0.5 rounded text-[10px] text-foreground">
                  {d.nodes.length} tags
                </span>
              </div>

              <h4 className="text-xs font-semibold text-foreground leading-snug line-clamp-1">
                {d.drawingTitle}
              </h4>

              <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                {d.description}
              </p>
            </Card>
          )
        })}
      </div>

      {/* Active P&ID Interactive Workbench View */}
      <Card className="border-border/80 p-4 md:p-6 bg-card rounded-2xl shadow-none">
        <PIDGraphViewer graphData={activeGraph} isFullScreen={true} />
      </Card>
    </div>
  )
}
