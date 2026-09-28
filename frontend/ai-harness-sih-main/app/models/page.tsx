"use client"

import React, { useState, useMemo } from "react"
import {
  Brain,
  Calculator,
  Eye,
  Check,
  Plus,
  Search,
  Cpu,
  Layers,
  Trash2,
  CheckCircle2,
  AlertCircle,
  X,
  Zap,
} from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useWorkbench } from "@/lib/workbench-context"
import { ModelRegistryItem, ModelRole } from "@/types/workbench"
import { apiClient } from "@/lib/api-client"
import { modelsConfig } from "@/lib/config"
import { cn } from "@/lib/utils"

/**
 * Presets offered in the "register model" dialog.
 *
 * Intentionally empty. Prescribing hosted models here ("OpenAI on Groq LPU", etc.)
 * misrepresents the deployment: Indigent runs local weights through Ollama, and the
 * authoritative list of what is actually available is whatever `/api/models` returns.
 * A preset would also imply the model can be fetched, which nothing in this app does.
 */
const MODEL_PRESETS: Partial<ModelRegistryItem>[] = []

export default function ModelsPage() {
  const { activeModelId, setActiveModelId } = useWorkbench()
  const [models, setModels] = useState<ModelRegistryItem[]>([])
  const [isLoadingModels, setIsLoadingModels] = useState<boolean>(true)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedRoleFilter, setSelectedRoleFilter] = useState<string>("all")
  // Unknown until the backend reports it. Never a hardcoded vendor model id.
  const [activeDriverId, setActiveDriverId] = useState<string>(activeModelId || "")
  const [hardwareInfo, setHardwareInfo] = useState<{
    activeMode: string
    profile: string
    vramMbFree: number
    ramMbFree: number
    diskMbFree: number
    maxConcurrency: number
  } | null>(null)

  React.useEffect(() => {
    setIsLoadingModels(true)
    apiClient
      .getModels()
      .then((data) => {
        // Map only what the backend actually reports. The /api/models payload is
        // {id, type, tasks, provider, model_name, available, resident, memory_estimate_mb}
        // — it carries no quantization, context length, engine or vendor branding, so
        // none of those are invented here. See Frontend-fix.md item 1.6.
        const raw = Array.isArray(data?.models) ? data.models : []
        const mapped: ModelRegistryItem[] = raw.map((m) => {
          const rec = m as Record<string, unknown>
          const memoryMb = typeof rec.memory_estimate_mb === "number" ? rec.memory_estimate_mb : undefined
          const isResident = rec.resident === true
          return {
            id: String(rec.id ?? ""),
            name: typeof rec.model_name === "string" ? rec.model_name : String(rec.id ?? "Unnamed model"),
            role: (typeof rec.type === "string" ? rec.type : "general") as ModelRole,
            tasks: Array.isArray(rec.tasks) ? rec.tasks.map(String) : [],
            ...(typeof rec.provider === "string" ? { provider: rec.provider, authorOrOrg: rec.provider } : {}),
            ...(memoryMb !== undefined ? { vramGb: Math.round((memoryMb / 1024) * 10) / 10 } : {}),
            isResident,
            priority: 1,
            architecture: String(rec.id ?? ""),
            status: isResident ? "resident" : rec.available === false ? "standby" : "available",
          }
        })
        setModels(mapped)
        if (data.active_model_id) {
          setActiveDriverId(data.active_model_id)
        } else {
          setActiveDriverId(mapped.find((m) => m.isResident)?.id ?? "")
        }
        if (data?.resources) {
          setHardwareInfo({
            activeMode: data.active_inference_mode || "unknown",
            profile: data.hardware_profile || "unknown",
            vramMbFree: data.resources.vram_mb_free,
            ramMbFree: data.resources.ram_mb_free,
            diskMbFree: data.resources.disk_mb_free,
            maxConcurrency: data.resources.max_concurrency,
          })
        }
      })
      .catch((err) => {
        setModels([])
        setModelsError(err instanceof Error ? err.message : "Failed to reach the backend")
      })
      .finally(() => setIsLoadingModels(false))
  }, [])

  // Modal States
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [benchmarkModel, setBenchmarkModel] = useState<ModelRegistryItem | null>(null)
  const [isBenchmarking, setIsBenchmarking] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [isRegistering, setIsRegistering] = useState(false)
  const [registerError, setRegisterError] = useState<string | null>(null)

  // Add Model Form State.
  // Blank by default — the previous seed values ("70B", "Open Weights",
  // "/opt/models/gguf/model-70b.gguf", "Q4_K_M", 128000, 40.0) were invented and
  // were submitted as if the operator had supplied them.
  const [newModelForm, setNewModelForm] = useState({
    name: "",
    paramCount: "",
    role: "reasoning" as ModelRole,
    authorOrOrg: "",
    filePath: "",
    quantization: "",
    contextLength: "",
    vramGb: "",
    tasksInput: "",
  })

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3500)
  }

  const getRoleLabel = (role: ModelRole) => {
    switch (role) {
      case "reasoning":
        return "Reasoning"
      case "coding":
        return "Code & Math"
      case "vision":
        return "Vision & P&ID"
      case "embedding":
        return "RAG & Retrieval"
      default:
        return "General"
    }
  }

  const getRoleIcon = (role: ModelRole) => {
    switch (role) {
      case "reasoning":
        return <Brain className="size-4 text-muted-foreground" />
      case "coding":
        return <Calculator className="size-4 text-muted-foreground" />
      case "vision":
        return <Eye className="size-4 text-muted-foreground" />
      case "embedding":
        return <Layers className="size-4 text-muted-foreground" />
      default:
        return <Cpu className="size-4 text-muted-foreground" />
    }
  }

  // Filtered models
  const filteredModels = useMemo(() => {
    return models.filter((m) => {
      const matchesSearch =
        m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.authorOrOrg?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.paramCount?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.tasks.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()))

      const matchesRole = selectedRoleFilter === "all" || m.role === selectedRoleFilter
      return matchesSearch && matchesRole
    })
  }, [models, searchQuery, selectedRoleFilter])

  /**
   * The model currently driving inference, or undefined when the backend reports none.
   * There is deliberately no hardcoded vendor fallback: with no models loaded the UI
   * must say so rather than name a hosted model that is not present.
   */
  const activeModel = useMemo<ModelRegistryItem | undefined>(() => {
    if (models.length === 0) return undefined
    return models.find((m) => m.id === activeDriverId) ?? models.find((m) => m.isResident) ?? models[0]
  }, [models, activeDriverId])

  const handleSetActiveDriver = async (modelId: string) => {
    setActiveDriverId(modelId)
    setModels((prev) =>
      prev.map((m) => ({
        ...m,
        isResident: m.id === modelId,
        status: m.id === modelId ? "resident" : "standby",
      }))
    )
    const targetModel = models.find((m) => m.id === modelId)
    try {
      await setActiveModelId(modelId)
      showToast(`Active inference driver set to ${targetModel?.name || modelId}`)
    } catch {
      showToast(`Selected ${targetModel?.name || modelId}`)
    }
  }

  const handleToggleResidency = (modelId: string) => {
    setModels((prev) =>
      prev.map((m) => {
        if (m.id === modelId) {
          const nextResident = !m.isResident
          return {
            ...m,
            isResident: nextResident,
            status: nextResident ? "resident" : "standby",
          }
        }
        return m
      })
    )
    const target = models.find((m) => m.id === modelId)
    showToast(
      target?.isResident
        ? `Unloaded ${target.name} to storage standby.`
        : `Loaded ${target?.name} into memory cache.`
    )
  }

  const handleDeleteModel = (modelId: string) => {
    // No backend route exists for removing a model (app/api/models.py exposes only
    // GET /models, POST /models, POST /models/active). Deleting from local state would
    // show a success toast for a change that is lost on the next reload, so the button
    // is disabled with an explanation rather than faking the removal.
    const target = models.find((m) => m.id === modelId)
    showToast(
      `Cannot remove "${target?.name ?? modelId}" — the backend exposes no delete route for models.`
    )
  }

  const handleApplyPreset = (preset: Partial<ModelRegistryItem>) => {
    setNewModelForm({
      name: preset.name ?? "",
      paramCount: preset.paramCount ?? "",
      role: preset.role ?? "reasoning",
      authorOrOrg: preset.authorOrOrg ?? "",
      filePath: preset.filePath ?? "",
      quantization: preset.quantization ?? "",
      contextLength: preset.contextLength !== undefined ? String(preset.contextLength) : "",
      vramGb: preset.vramGb !== undefined ? String(preset.vramGb) : "",
      tasksInput: preset.tasks?.join(", ") ?? "",
    })
  }

  const handleAddModelSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newModelForm.name.trim() || isRegistering) return

    const id = `custom-${Date.now()}`
    const tasks = newModelForm.tasksInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)

    setIsRegistering(true)
    setRegisterError(null)
    try {
      // Persist server-side. Previously this only mutated local React state, so a
      // "registered" model silently disappeared on reload while reporting success.
      const res = await apiClient.registerModel({
        id,
        name: newModelForm.name.trim(),
        role: newModelForm.role,
        tasks,
      })

      // The response echoes the payload with the server's pydantic defaults filled in.
      // Render only what we actually sent, and mark defaulted fields as unverified.
      const echoed = (res.model ?? {}) as Record<string, unknown>
      const newModel: ModelRegistryItem = {
        id,
        name: newModelForm.name.trim(),
        role: newModelForm.role as ModelRole,
        tasks,
        isResident: false,
        priority: 2,
        status: "standby",
        isCustom: true,
        ...(newModelForm.filePath.trim() ? { filePath: newModelForm.filePath.trim() } : {}),
        // Only shown when explicitly supplied by the operator.
        ...(newModelForm.paramCount.trim() ? { paramCount: newModelForm.paramCount.trim() } : {}),
        ...(newModelForm.authorOrOrg.trim()
          ? { authorOrOrg: newModelForm.authorOrOrg.trim() }
          : {}),
        ...(newModelForm.quantization.trim()
          ? { quantization: newModelForm.quantization.trim() }
          : {}),
        ...(newModelForm.contextLength.trim()
          ? { contextLength: Number(newModelForm.contextLength) }
          : {}),
      }

      setModels((prev) => [newModel, ...prev])
      setIsAddModalOpen(false)
      showToast(
        `Registered ${newModel.name}. Server defaults applied to unspecified fields` +
          (echoed.paramCount ? ` (e.g. paramCount "${String(echoed.paramCount)}")` : "") +
          " — these are unverified placeholders, not measurements."
      )
      setNewModelForm({
        name: "",
        paramCount: "",
        role: "reasoning",
        authorOrOrg: "",
        filePath: "",
        quantization: "",
        contextLength: "",
        vramGb: "",
        tasksInput: "",
      })
    } catch (err) {
      setRegisterError(
        err instanceof Error ? `Registration failed: ${err.message}` : "Registration failed"
      )
    } finally {
      setIsRegistering(false)
    }
  }

  const handleStartBenchmark = (model: ModelRegistryItem) => {
    // There is no benchmark route in app/api/models.py. The previous implementation
    // slept 800ms and displayed 26.4 tok/s / 140 ms TTFT as if measured. Removed
    // rather than labelled — see Frontend-fix.md item 1.12.
    setBenchmarkModel(model)
    setIsBenchmarking(false)
    showToast("No benchmark endpoint exists — throughput and TTFT are not measured by this system.")
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 max-w-6xl mx-auto">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg bg-card border border-border px-4 py-3 text-xs text-foreground shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-150">
          <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold tracking-tight text-foreground">
              {modelsConfig.title}
            </h1>
            <span className="text-xs text-muted-foreground">· {modelsConfig.tier}</span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {modelsConfig.subtitle}
          </p>
        </div>

        <Button
          size="sm"
          onClick={() => setIsAddModalOpen(true)}
          className="text-xs h-8.5 font-medium gap-1.5 px-3.5 cursor-pointer"
        >
          <Plus className="size-3.5" />
          <span>{modelsConfig.addButton}</span>
        </Button>
      </div>

      {/* Clean Status Summary Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-3.5 rounded-lg bg-card border border-border">
          <span className="text-[11px] text-muted-foreground block">{modelsConfig.activeEngine}</span>
          <div className="flex items-center gap-2 mt-1">
            {/* Pulse only when a model is genuinely loaded and resident. */}
            <span
              className={cn(
                "size-2 rounded-full shrink-0",
                activeModel?.isResident ? "bg-emerald-500 animate-pulse" : "bg-neutral-600"
              )}
            />
            <span className="text-xs font-semibold text-foreground truncate">
              {activeModel?.name ?? "No model loaded"}
            </span>
            {activeModel?.paramCount && (
              <Badge variant="secondary" className="text-[10px] py-0 px-1.5 font-mono">
                {activeModel.paramCount}
              </Badge>
            )}
            {activeModel?.provider && (
              <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                {activeModel.provider}
              </Badge>
            )}
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-card border border-border">
          <span className="text-[11px] text-muted-foreground block">{modelsConfig.memoryFootprint}</span>
          <div className="text-xs font-semibold text-foreground mt-1">
            {activeModel?.vramGb !== undefined ? (
              <>
                <span className="font-mono">{activeModel.vramGb} GB</span>
                {hardwareInfo && (
                  <span className="text-muted-foreground font-normal ml-1.5 text-[11px]">
                    / {Math.round(hardwareInfo.ramMbFree / 1024)} GB system RAM free
                  </span>
                )}
              </>
            ) : (
              <span className="text-muted-foreground">
                {activeModel ? "Not reported by the backend" : "No model loaded"}
              </span>
            )}
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-card border border-border">
          <span className="text-[11px] text-muted-foreground block">{modelsConfig.localArchitecture}</span>
          <div className="text-xs font-semibold text-foreground mt-1">
            {hardwareInfo
              ? `Mode: ${hardwareInfo.activeMode} · Profile: ${hardwareInfo.profile}`
              : "Not reported by the backend"}
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-1">
        <div className="relative flex-1 max-w-sm">
          <Search className="size-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          <Input
            type="text"
            placeholder="Search model, parameter, or task..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8.5 h-8.5 text-xs bg-background rounded-md border-border"
          />
        </div>

        <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
          {["all", "reasoning", "coding", "vision", "embedding"].map((role) => (
            <button
              key={role}
              onClick={() => setSelectedRoleFilter(role)}
              className={cn(
                "px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors capitalize",
                selectedRoleFilter === role
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              )}
            >
              {role === "all" ? "All" : getRoleLabel(role as ModelRole)}
            </button>
          ))}
        </div>
      </div>

      {/* Model load failure — never silently fall back to a placeholder registry */}
      {modelsError && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-xl border border-red-500/40 bg-red-500/5 p-4 text-xs text-foreground"
        >
          <AlertCircle className="size-4 text-red-500 shrink-0 mt-px" />
          <div className="space-y-1">
            <p className="font-semibold">Could not load models from the backend.</p>
            <p className="text-muted-foreground">{modelsError}</p>
            <p className="text-muted-foreground">
              No model data is being shown, because none was returned. Check that the API is
              running and that <code className="font-mono">JOY_MODULES</code> resolves.
            </p>
          </div>
        </div>
      )}

      {/* Model Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {!isLoadingModels && !modelsError && models.length === 0 && (
          <div className="col-span-full flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border/70 py-14 text-center">
            <Cpu className="size-6 text-neutral-600" />
            <p className="text-sm font-medium text-foreground">No models are registered</p>
            <p className="max-w-md text-xs text-muted-foreground">
              The backend reported an empty model list. Nothing is loaded and no default
              model is assumed.
            </p>
          </div>
        )}
        {filteredModels.map((model) => {
          const isCurrentlyActive = activeDriverId === model.id
          return (
            <Card
              key={model.id}
              className={cn(
                "p-4 rounded-lg bg-card border transition-colors flex flex-col justify-between shadow-none",
                isCurrentlyActive
                  ? "border-emerald-500/60"
                  : "border-border hover:border-border/80"
              )}
            >
              <div>
                {/* Card Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="flex size-8 items-center justify-center rounded-md bg-secondary text-foreground">
                      {getRoleIcon(model.role)}
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <h3 className="text-xs font-semibold text-foreground">
                          {model.name}
                        </h3>
                        {model.paramCount && (
                          <span className="text-[11px] font-mono text-muted-foreground bg-secondary px-1.5 py-0.2 rounded">
                            {model.paramCount}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        {[model.authorOrOrg, getRoleLabel(model.role)].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                  </div>

                  <div>
                    {isCurrentlyActive ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-500 font-medium bg-emerald-500/10 px-2 py-0.5 rounded">
                        <span className="size-1.5 rounded-full bg-emerald-500" />
                        Active
                      </span>
                    ) : (
                      <span className="text-[11px] text-muted-foreground bg-secondary px-2 py-0.5 rounded">
                        {model.isResident ? "Loaded" : "Standby"}
                      </span>
                    )}
                  </div>
                </div>

                {/* Tasks Summary */}
                <p className="text-[11px] text-muted-foreground mt-3 line-clamp-1">
                  {model.tasks.join(" · ")}
                </p>

                {/* Specs Row — the backend reports none of these for local models, so
                    each cell degrades to an explicit dash instead of an invented spec. */}
                <div className="grid grid-cols-3 gap-2 mt-3 pt-2.5 border-t border-border/60 text-[11px]">
                  <div>
                    <span className="text-muted-foreground text-[10px] block">Context</span>
                    <span className="font-mono text-foreground">
                      {typeof model.contextLength === "number"
                        ? `${(model.contextLength / 1000).toFixed(0)}k`
                        : (model.contextLength ?? "—")}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground text-[10px] block">Quantization</span>
                    <span className="font-mono text-foreground">{model.quantization ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground text-[10px] block">Memory</span>
                    <span className="font-mono text-foreground">
                      {model.vramGb !== undefined ? `${model.vramGb} GB` : "—"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Actions Toolbar */}
              <div className="mt-4 pt-2.5 border-t border-border/60 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant={isCurrentlyActive ? "secondary" : "outline"}
                    onClick={() => handleSetActiveDriver(model.id)}
                    disabled={isCurrentlyActive}
                    className="text-xs h-7.5 px-2.5 font-medium"
                  >
                    {isCurrentlyActive ? (
                      <span className="flex items-center gap-1 text-emerald-500">
                        <Check className="size-3" />
                        Active Driver
                      </span>
                    ) : (
                      "Set as Active"
                    )}
                  </Button>

                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleToggleResidency(model.id)}
                    className="text-xs h-7.5 px-2 text-muted-foreground hover:text-foreground"
                  >
                    {model.isResident ? "Unload" : "Load"}
                  </Button>
                </div>

                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleStartBenchmark(model)}
                    className="text-xs h-7.5 px-2 text-muted-foreground hover:text-foreground"
                  >
                    <Zap className="size-3 mr-1" />
                    Test
                  </Button>

                  {model.isCustom && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDeleteModel(model.id)}
                      className="text-xs h-7.5 px-1.5 text-muted-foreground hover:text-red-500"
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      {/* Add Model Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-100">
          <div className="bg-card border border-border rounded-lg w-full max-w-lg shadow-xl p-5 relative">
            <button
              onClick={() => setIsAddModalOpen(false)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground p-1 rounded"
            >
              <X className="size-4" />
            </button>

            <div className="pb-3 border-b border-border">
              <h2 className="text-sm font-semibold text-foreground">Register Local Model</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Add a locally hosted 70B–120B GGUF or SafeTensors weight file.
              </p>
            </div>

            {/* Presets */}
            <div className="mt-3.5">
              <label className="text-[11px] text-muted-foreground block mb-1">
                Quick Presets
              </label>
              <div className="flex flex-wrap gap-1.5">
                {MODEL_PRESETS.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    onClick={() => handleApplyPreset(preset)}
                    className="text-[11px] bg-secondary hover:bg-secondary/80 text-foreground px-2 py-0.5 rounded border border-border transition-colors"
                  >
                    {preset.name} ({preset.paramCount})
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleAddModelSubmit} className="mt-4 space-y-3">
              {registerError && (
                <div
                  role="alert"
                  className="flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/5 p-2.5 text-[11px] text-foreground"
                >
                  <AlertCircle className="size-3.5 text-red-500 shrink-0 mt-px" />
                  <span>{registerError}</span>
                </div>
              )}
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="text-[11px] text-foreground block mb-1">
                    Model Name *
                  </label>
                  <Input
                    required
                    placeholder="e.g. DeepSeek-R1 Distill Llama"
                    value={newModelForm.name}
                    onChange={(e) => setNewModelForm({ ...newModelForm, name: e.target.value })}
                    className="text-xs h-8"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-foreground block mb-1">
                    Params
                  </label>
                  <Input
                    placeholder="70B / 120B"
                    value={newModelForm.paramCount}
                    onChange={(e) => setNewModelForm({ ...newModelForm, paramCount: e.target.value })}
                    className="text-xs h-8 font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-foreground block mb-1">
                    Role *
                  </label>
                  <select
                    value={newModelForm.role}
                    onChange={(e) => setNewModelForm({ ...newModelForm, role: e.target.value as ModelRole })}
                    className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground focus:outline-none"
                  >
                    <option value="reasoning">Reasoning &amp; SOP</option>
                    <option value="coding">Code &amp; Math</option>
                    <option value="vision">Vision &amp; P&amp;ID</option>
                    <option value="embedding">RAG &amp; Retrieval</option>
                  </select>
                </div>
                <div>
                  <label className="text-[11px] text-foreground block mb-1">
                    Organization
                  </label>
                  <Input
                    placeholder="e.g. DeepSeek AI"
                    value={newModelForm.authorOrOrg}
                    onChange={(e) => setNewModelForm({ ...newModelForm, authorOrOrg: e.target.value })}
                    className="text-xs h-8"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] text-foreground block mb-1">
                  Local File Path *
                </label>
                <Input
                  required
                  placeholder="/opt/models/gguf/model-70b.gguf"
                  value={newModelForm.filePath}
                  onChange={(e) => setNewModelForm({ ...newModelForm, filePath: e.target.value })}
                  className="text-xs h-8 font-mono"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[11px] text-foreground block mb-1">
                    Quantization
                  </label>
                  <Input
                    value={newModelForm.quantization}
                    onChange={(e) => setNewModelForm({ ...newModelForm, quantization: e.target.value })}
                    className="text-xs h-8 font-mono"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-foreground block mb-1">
                    Context Window
                  </label>
                  <select
                    value={newModelForm.contextLength}
                    onChange={(e) => setNewModelForm({ ...newModelForm, contextLength: e.target.value })}
                    className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground focus:outline-none font-mono"
                  >
                    <option value="">Not specified</option>
                    <option value="32000">32k</option>
                    <option value="64000">64k</option>
                    <option value="128000">128k</option>
                  </select>
                </div>
                <div>
                  <label className="text-[11px] text-foreground block mb-1">
                    Memory (GB)
                  </label>
                  <Input
                    type="number"
                    step="0.5"
                    value={newModelForm.vramGb}
                    onChange={(e) => setNewModelForm({ ...newModelForm, vramGb: e.target.value })}
                    className="text-xs h-8 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] text-foreground block mb-1">
                  Task Capabilities (comma separated)
                </label>
                <Input
                  placeholder="SOP Verification, Regulatory Analysis"
                  value={newModelForm.tasksInput}
                  onChange={(e) => setNewModelForm({ ...newModelForm, tasksInput: e.target.value })}
                  className="text-xs h-8"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsAddModalOpen(false)}
                  className="text-xs h-8"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={isRegistering}
                  className="text-xs h-8 font-medium px-4"
                >
                  {isRegistering ? "Registering…" : "Register Model"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Benchmark Modal */}
      {benchmarkModel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-100">
          <div className="bg-card border border-border rounded-lg w-full max-w-sm shadow-xl p-5 relative">
            <button
              onClick={() => setBenchmarkModel(null)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground p-1 rounded"
            >
              <X className="size-4" />
            </button>

            <div className="pb-3 border-b border-border">
              <h2 className="text-sm font-semibold text-foreground">Local Inference Diagnostic</h2>
              <p className="text-xs text-muted-foreground">
                {benchmarkModel.name}
                {benchmarkModel.paramCount ? ` (${benchmarkModel.paramCount})` : ""}
              </p>
            </div>

            <div className="mt-4 space-y-3">
              {isBenchmarking ? (
                <div className="py-6 text-center text-xs text-muted-foreground">
                  Running local test evaluation on device...
                </div>
              ) : (
                <div className="space-y-2 text-xs text-muted-foreground">
                  <p>
                    Throughput, time-to-first-token and memory allocation are{" "}
                    <span className="text-foreground font-medium">not measured</span> by this
                    system.
                  </p>
                  <p className="text-[11px]">
                    <code className="font-mono">app/api/models.py</code> exposes no benchmark
                    route, so no figure is available to display here. This dialog previously
                    showed invented values (26.4 tok/s, 140 ms) and an &quot;air-gap
                    verification passed&quot; claim that no code performed.
                  </p>
                  <p className="text-[11px]">
                    Live egress counters are available on the Sovereignty Monitor, which reads{" "}
                    <code className="font-mono">/api/monitoring/sovereignty</code>.
                  </p>
                </div>
              )}

              <div className="flex justify-end pt-2 border-t border-border">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setBenchmarkModel(null)}
                  className="text-xs h-7.5"
                >
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
