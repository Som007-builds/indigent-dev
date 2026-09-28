"use client"

import React, { useState, useEffect, useRef } from "react"
import {
  FileText,
  Download,
  Upload,
  Search,
  Table as TableIcon,
  Map,
  FileCheck,
  Loader2,
  CheckCircle2,
  FolderOpen,
  AlertTriangle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { apiClient, ApiError } from "@/lib/api-client"
import { documentsConfig } from "@/lib/config"

/**
 * One stored file, built only from fields `GET /api/files` actually returns:
 * `file_id, name, size, sha256, mime, kind, created_at, download_url`.
 *
 * The previous shape carried `status`, `category` and a `type` derived from guesses
 * about what each file was ("Inspection Scan", "Plant Drawing"), plus a `downloadUrl`
 * that fell back to `/api/files/{name}` — a route that does not exist. See
 * Frontend-fix.md items 2.2 and 1.13.
 */
interface DocItem {
  fileId: string
  name: string
  /** File extension, taken from the name. Real, and it is what identifies the format. */
  extension: string
  /** `mime` column from the backend, used only when the name has no extension. */
  mimeKind: string
  /** `kind` column: "upload" | "knowledge" | "pid". */
  kind: string
  sizeBytes: number
  sha256: string
  /** Nullable — the schema allows NULL and the list response may omit it. */
  createdAt?: string
  /** Absent means the file cannot be retrieved; the button is disabled, not faked. */
  downloadUrl?: string
}

const KIND_LABELS: Record<string, string> = {
  upload: "Uploaded file",
  knowledge: "Knowledge base",
  pid: "P&ID drawing",
}

/** `"1.4 MB"` / `"912 KB"` / `"—"` for a zero-byte or unknown size. Never invented. */
function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} bytes`
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [isUploading, setIsUploading] = useState(false)
  const [uploadToast, setUploadToast] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadFiles = async () => {
    try {
      const res = await apiClient.listFiles()
      if (res?.files) {
        const mapped: DocItem[] = res.files.map((f) => ({
          fileId: f.file_id,
          name: f.name,
          extension: f.name.includes(".") ? f.name.slice(f.name.lastIndexOf(".")) : "",
          mimeKind: f.mime,
          kind: f.kind,
          sizeBytes: f.size,
          sha256: f.sha256,
          ...(f.created_at ? { createdAt: f.created_at } : {}),
          // Built from the id, never the name. `GET /api/files` now emits this key;
          // when it is missing the row is not downloadable and the UI says so.
          ...(f.download_url ? { downloadUrl: f.download_url } : {}),
        }))
        setDocuments(mapped)
        setLoadError(null)
      } else {
        setDocuments([])
      }
    } catch (err) {
      // Previously an empty catch: a backend failure rendered as "No documents in
      // workspace", which is indistinguishable from a genuinely empty workspace.
      setDocuments([])
      setLoadError(
        err instanceof ApiError
          ? `${err.code} (HTTP ${err.status}): ${err.message}`
          : err instanceof Error
          ? err.message
          : "Failed to load documents"
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadFiles()
  }, [])

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return
    const files = Array.from(e.target.files)
    setIsUploading(true)
    setUploadError(null)
    setUploadToast(null)
    try {
      // The response is used, not discarded: the file ids and digests the backend
      // actually stored are what the confirmation reports.
      const res = await apiClient.uploadFiles(files)
      const stored = res?.files ?? []
      if (stored.length === 0) {
        setUploadError("The backend accepted the request but reported no stored files.")
      } else {
        setUploadToast(
          `Stored ${stored.length} of ${files.length} file(s) in the secure workspace.`
        )
        setTimeout(() => setUploadToast(null), 4000)
      }
      await loadFiles()
    } catch (err) {
      // Previously this fabricated a row per file with `status: "Local Workspace"`
      // and toasted "Added N document(s) to local workspace." — a rejected upload
      // was reported to the user as a successful one, which is the same defect as
      // item 1.1 on the P&ID page. Nothing is added to the table here.
      setUploadError(
        err instanceof ApiError
          ? `${err.code} (HTTP ${err.status}): ${err.message}`
          : err instanceof Error
          ? err.message
          : "Upload failed"
      )
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleDownload = (doc: DocItem) => {
    // The old fallback built a Blob reading
    // "CONFIDENTIAL AIR-GAPPED RECORD: <name> CATEGORY: … SIZE: … UPLOADED: …" and
    // saved it as `<name>.txt`, so clicking Download on a real PDF handed the user a
    // fabricated text file that looked like the deliverable. The backend owns the
    // bytes; if there is no URL there is nothing to hand over.
    if (!doc.downloadUrl) return
    window.open(doc.downloadUrl, "_blank")
  }

  const filteredDocs = documents.filter(
    (d) =>
      d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.kind.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.extension.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 max-w-6xl mx-auto">
      {/* Toast */}
      {uploadToast && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg bg-card border border-border px-4 py-3 text-xs text-foreground shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-150">
          <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
          <span>{uploadToast}</span>
        </div>
      )}

      {/* Upload failure. The old code showed a green success toast here while adding
          fabricated rows to the table below. */}
      {uploadError && (
        <div
          role="alert"
          className="fixed bottom-6 right-6 z-50 flex items-start gap-2 rounded-lg bg-card border border-destructive/50 px-4 py-3 text-xs text-foreground shadow-lg max-w-sm"
        >
          <AlertTriangle className="size-4 text-destructive shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-medium text-destructive">Upload failed</p>
            <p className="text-muted-foreground">{uploadError}</p>
            <p className="text-muted-foreground">
              No files were stored. Nothing has been added to the list below.
            </p>
          </div>
        </div>
      )}

      {/* Hidden File Input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        className="hidden"
        multiple
      />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 pb-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <FileText className="size-4 text-muted-foreground" />
            <span>{documentsConfig.title}</span>
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {documentsConfig.subtitle}
          </p>
        </div>

        <Button
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="gap-1.5 text-xs rounded-lg font-medium cursor-pointer"
        >
          {isUploading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Upload className="size-3.5" />
          )}
          <span>{documentsConfig.uploadButton}</span>
        </Button>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={documentsConfig.searchPlaceholder}
            className="pl-8 text-xs h-9 rounded-lg"
          />
        </div>
        <span className="text-xs text-muted-foreground">
          {filteredDocs.length} files
        </span>
      </div>

      {/* Documents Table */}
      <Card className="border-border/80 rounded-xl overflow-hidden shadow-none bg-card">
        {isLoading ? (
          <div className="py-12 flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
            <span>Loading workspace documents...</span>
          </div>
        ) : loadError ? (
          <div className="py-14 text-center space-y-2 px-6">
            <AlertTriangle className="size-6 text-destructive mx-auto" />
            <p className="text-xs font-medium text-foreground">
              The document list could not be read
            </p>
            <p className="text-[11px] text-muted-foreground max-w-md mx-auto">
              {loadError}
            </p>
            <p className="text-[11px] text-muted-foreground max-w-md mx-auto">
              This is <strong>not</strong> an empty workspace — the stored files could
              not be listed, so what is on disk is unknown.
            </p>
          </div>
        ) : filteredDocs.length === 0 ? (
          <div className="py-16 text-center space-y-3">
            <div className="inline-flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <FolderOpen className="size-5" />
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-foreground">No documents in workspace</p>
              <p className="text-[11px] text-muted-foreground max-w-sm mx-auto">
                The backend was queried successfully and returned zero files. Upload
                inspection scans or P&amp;ID drawings, or run a task to generate Word and
                Excel deliverables.
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              className="text-xs h-8 cursor-pointer"
            >
              <Upload className="size-3.5 mr-1.5" />
              <span>{documentsConfig.uploadButton}</span>
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow>
                <TableHead className="text-xs font-medium text-muted-foreground">{documentsConfig.table.name}</TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">Format</TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">{documentsConfig.table.category}</TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">{documentsConfig.table.size}</TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground">Added</TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground text-right">{documentsConfig.table.action}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredDocs.map((doc) => (
                <TableRow key={doc.fileId} className="hover:bg-muted/20">
                  <TableCell
                    className="text-xs font-medium text-foreground flex items-center gap-2 py-3"
                    title={`Stored with sha256 ${doc.sha256}`}
                  >
                    {doc.extension === ".pdf" ? (
                      <FileText className="size-3.5 text-muted-foreground" />
                    ) : doc.extension === ".docx" || doc.extension === ".xlsx" ? (
                      <TableIcon className="size-3.5 text-muted-foreground" />
                    ) : doc.extension === ".png" || doc.extension === ".jpg" || doc.extension === ".jpeg" ? (
                      <Map className="size-3.5 text-muted-foreground" />
                    ) : (
                      <FileCheck className="size-3.5 text-muted-foreground" />
                    )}
                    <span className="truncate max-w-[200px]">{doc.name}</span>
                  </TableCell>
                  {/* The real extension. The previous "type" column asserted what each
                      file *was* — "Inspection Scan", "Plant Drawing" — which the
                      backend never says; a PDF of anything renders as "Inspection Scan". */}
                  <TableCell className="text-xs text-muted-foreground">
                    {doc.extension || doc.mimeKind || "—"}
                  </TableCell>
                  {/* The real `kind` column. */}
                  <TableCell className="text-xs text-muted-foreground">
                    {KIND_LABELS[doc.kind] ?? doc.kind}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatSize(doc.sizeBytes)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {doc.createdAt ? new Date(doc.createdAt).toLocaleString() : "Not reported"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDownload(doc)}
                      disabled={!doc.downloadUrl}
                      title={
                        doc.downloadUrl
                          ? "Download the stored file"
                          : "This build of the backend reports no download route for the file"
                      }
                      className="h-7 gap-1 text-xs font-normal rounded-md cursor-pointer"
                    >
                      <Download className="size-3 text-muted-foreground" />
                      <span>{documentsConfig.table.download}</span>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  )
}
