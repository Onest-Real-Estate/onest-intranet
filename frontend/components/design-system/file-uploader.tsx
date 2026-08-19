import {
  AlertCircle,
  CheckCircle2,
  File,
  Image as ImageIcon,
  LoaderCircle,
  RefreshCw,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export interface UploadedFile {
  id?: string;
  name: string;
  url?: string;
  size?: number;
  type?: string;
}

export interface UploadContext {
  signal: AbortSignal;
  onProgress: (progress: number) => void;
}

export type UploadHandler = (
  file: globalThis.File,
  context: UploadContext,
) => Promise<UploadedFile>;

type UploadState = "idle" | "uploading" | "success" | "error";

function formatBytes(bytes: number | undefined): string | null {
  if (bytes === undefined) return null;
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function FileUploader({
  label = "Upload file",
  description,
  accept,
  maxSize,
  value = null,
  upload,
  validate,
  onChange,
  disabled = false,
  readOnly = false,
  preview = true,
  removable = true,
  className,
}: {
  label?: string;
  description?: string;
  accept?: string;
  maxSize?: number;
  value?: UploadedFile | null;
  upload: UploadHandler;
  validate?: (file: globalThis.File) => string | null;
  onChange?: (file: UploadedFile | null) => void;
  disabled?: boolean;
  readOnly?: boolean;
  preview?: boolean;
  removable?: boolean;
  className?: string;
}) {
  const id = useId();
  const descriptionId = `${id}-description`;
  const statusId = `${id}-status`;
  const inputRef = useRef<HTMLInputElement>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<UploadState>(value ? "success" : "idle");
  const [progress, setProgress] = useState(value ? 100 : 0);
  const [error, setError] = useState<string | null>(null);
  const [lastFile, setLastFile] = useState<globalThis.File | null>(null);
  const [uploaded, setUploaded] = useState<UploadedFile | null>(value);
  const [dragging, setDragging] = useState(false);
  const localPreview = useMemo(
    () => (lastFile?.type.startsWith("image/") ? URL.createObjectURL(lastFile) : null),
    [lastFile],
  );

  useEffect(() => {
    return () => {
      if (localPreview) URL.revokeObjectURL(localPreview);
      controllerRef.current?.abort();
    };
  }, [localPreview]);

  async function startUpload(file: globalThis.File) {
    setLastFile(file);
    setError(null);
    if (maxSize && file.size > maxSize) {
      setState("error");
      setError(`Choose a file smaller than ${formatBytes(maxSize)}.`);
      return;
    }
    const clientError = validate?.(file);
    if (clientError) {
      setState("error");
      setError(clientError);
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    setState("uploading");
    setProgress(5);
    try {
      const result = await upload(file, {
        signal: controller.signal,
        onProgress: (next) => setProgress(Math.min(100, Math.max(0, next))),
      });
      setUploaded(result);
      setProgress(100);
      setState("success");
      onChange?.(result);
    } catch (uploadError) {
      if (controller.signal.aborted) return;
      setState("error");
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Upload failed. Try again.",
      );
    }
  }

  const previewUrl = uploaded?.url ?? localPreview;
  const fileName = uploaded?.name ?? lastFile?.name;
  const fileSize = uploaded?.size ?? lastFile?.size;

  if (readOnly && uploaded) {
    return (
      <div className={cn("flex items-center gap-3 rounded-lg border p-3", className)}>
        <File className="text-muted-foreground size-5" aria-hidden />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{uploaded.name}</p>
          <p className="text-muted-foreground text-xs">Read-only</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("grid gap-3", className)}>
      <button
        type="button"
        className={cn(
          "focus-visible:ring-ring group relative grid min-h-40 place-items-center overflow-hidden rounded-xl border border-dashed p-5 text-center outline-none transition-[background-color,border-color,box-shadow] focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-50",
          dragging ? "border-primary bg-primary/5" : "border-input bg-muted/20",
          state === "error" && "border-destructive/50 bg-destructive/5",
          !disabled && "hover:border-primary/60 hover:bg-primary/4",
        )}
        disabled={disabled || state === "uploading"}
        aria-describedby={`${descriptionId} ${statusId}`}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setDragging(false);
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void startUpload(file);
        }}
      >
        {preview && previewUrl ? (
          <img
            src={previewUrl}
            alt="Selected file preview"
            className="absolute inset-0 size-full object-cover opacity-20"
          />
        ) : null}
        <span className="relative grid justify-items-center gap-2">
          <span className="brand-well text-primary grid size-10 place-items-center rounded-xl">
            {preview ? (
              <ImageIcon className="size-5" aria-hidden />
            ) : (
              <UploadCloud className="size-5" aria-hidden />
            )}
          </span>
          <span className="text-sm font-semibold">{fileName ?? label}</span>
          <span id={descriptionId} className="text-muted-foreground text-xs">
            {description ?? "Drag and drop, or press Enter to choose a file"}
          </span>
          {fileSize ? (
            <span className="text-muted-foreground text-xs">
              {formatBytes(fileSize)}
            </span>
          ) : null}
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        aria-label={`Choose file for ${label}`}
        className="sr-only"
        disabled={disabled}
        tabIndex={-1}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void startUpload(file);
          event.target.value = "";
        }}
      />
      <div id={statusId} aria-live="polite" className="min-h-5">
        {state === "uploading" ? (
          <div className="grid gap-1.5">
            <div className="text-muted-foreground flex items-center justify-between gap-3 text-xs">
              <span className="flex items-center gap-1.5">
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
                Uploading
              </span>
              <span>{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} aria-label="Upload progress" />
          </div>
        ) : null}
        {state === "success" ? (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-success flex items-center gap-1.5 text-sm">
              <CheckCircle2 className="size-4" aria-hidden />
              Upload complete
            </p>
            {removable ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setUploaded(null);
                  setLastFile(null);
                  setProgress(0);
                  setState("idle");
                  onChange?.(null);
                }}
              >
                <Trash2 className="size-4" aria-hidden />
                Remove
              </Button>
            ) : null}
          </div>
        ) : null}
        {state === "error" ? (
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p role="alert" className="text-destructive flex gap-1.5 text-sm">
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {error}
            </p>
            {lastFile ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void startUpload(lastFile)}
              >
                <RefreshCw className="size-4" aria-hidden />
                Retry
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
