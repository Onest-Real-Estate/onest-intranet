import { Calendar, CheckSquare, PenLine, Signature, Trash2, Type } from "lucide-react";
import { GlobalWorkerOptions, getDocument, type PDFDocumentProxy } from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  type DragEvent as ReactDragEvent,
  type PointerEvent as ReactPointerEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { loadProtectedPdfBytes } from "@/lib/protected-pdf";
import { cn } from "@/lib/utils";

GlobalWorkerOptions.workerSrc = pdfWorker;

export type TemplateFieldType = "text" | "signature" | "date" | "initials" | "checkbox";

export type TemplateFieldRole = "Prefill" | "Agent" | "Company";

export type TemplateFieldLayoutItem = {
  id: string;
  name: string;
  type: TemplateFieldType;
  role: TemplateFieldRole;
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
};

const PALETTE: Array<{
  type: TemplateFieldType;
  label: string;
  icon: typeof Type;
  hint: string;
  roles: TemplateFieldRole[];
}> = [
  {
    type: "signature",
    label: "Signature",
    icon: Signature,
    hint: "Drawn at signing",
    roles: ["Agent", "Company"],
  },
  {
    type: "initials",
    label: "Initials",
    icon: PenLine,
    hint: "Drawn at signing",
    roles: ["Agent", "Company"],
  },
  {
    type: "date",
    label: "Date",
    icon: Calendar,
    hint: "Signed-on or commercial date",
    roles: ["Prefill", "Agent", "Company"],
  },
  {
    type: "text",
    label: "Text",
    icon: Type,
    hint: "Fillable text",
    roles: ["Prefill", "Agent", "Company"],
  },
  {
    type: "checkbox",
    label: "Checkbox",
    icon: CheckSquare,
    hint: "Yes / no",
    roles: ["Prefill", "Agent", "Company"],
  },
];

const SIGNING_ONLY_TYPES = new Set<TemplateFieldType>(["signature", "initials"]);
const HUMAN_SIGNER_ROLES = new Set<TemplateFieldRole>(["Agent", "Company"]);

const DEFAULT_SIZE: Record<TemplateFieldType, { w: number; h: number }> = {
  text: { w: 180, h: 28 },
  signature: { w: 200, h: 56 },
  date: { w: 140, h: 28 },
  initials: { w: 80, h: 40 },
  checkbox: { w: 22, h: 22 },
};

const DND_MIME = "application/x-onest-field-type";

type PageSize = { width: number; height: number };

type ContractTemplateFieldPlacerProps = {
  pdfUrl: string;
  value: TemplateFieldLayoutItem[];
  onChange: (next: TemplateFieldLayoutItem[]) => void;
  readOnly?: boolean;
  className?: string;
  onSave?: () => void;
  saving?: boolean;
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `field-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function uniqueName(base: string, existing: TemplateFieldLayoutItem[]): string {
  const taken = new Set(existing.map((item) => item.name));
  if (!taken.has(base)) return base;
  let index = 2;
  while (taken.has(`${base}${index}`)) index += 1;
  return `${base}${index}`;
}

function defaultName(type: TemplateFieldType, role: TemplateFieldRole): string {
  if (role === "Agent") {
    if (type === "signature") return "AgentSignature";
    if (type === "date") return "AgentSignedOn";
    if (type === "initials") return "AgentInitials";
  }
  if (role === "Company") {
    if (type === "signature") return "CompanySignature";
    if (type === "date") return "CompanySignedOn";
    if (type === "initials") return "CompanyInitials";
  }
  const label = type[0]?.toUpperCase() + type.slice(1);
  return role === "Prefill" ? `Prefill${label}` : `${role}${label}`;
}

export function ContractTemplateFieldPlacer({
  pdfUrl,
  value,
  onChange,
  readOnly = false,
  className,
  onSave,
  saving = false,
}: ContractTemplateFieldPlacerProps) {
  const labelId = useId();
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const [viewerWidth, setViewerWidth] = useState(900);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pageSizes, setPageSizes] = useState<PageSize[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [placeRole, setPlaceRole] = useState<TemplateFieldRole>("Prefill");
  const [armedType, setArmedType] = useState<TemplateFieldType | null>(null);
  const dragRef = useRef<{
    id: string;
    mode: "move" | "resize";
    startX: number;
    startY: number;
    orig: TemplateFieldLayoutItem;
  } | null>(null);

  function setPlaceRoleSafe(role: TemplateFieldRole) {
    setPlaceRole(role);
    setArmedType((current) => {
      if (!current) return current;
      const meta = PALETTE.find((item) => item.type === current);
      return meta?.roles.includes(role) ? current : null;
    });
  }

  useEffect(() => {
    const node = viewerRef.current;
    if (!node) return;
    const update = () => setViewerWidth(node.clientWidth || 900);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let loadedDoc: PDFDocumentProxy | null = null;
    setLoadError(null);
    setDoc(null);
    setPageSizes([]);
    setLoading(true);

    void (async () => {
      try {
        const bytes = await loadProtectedPdfBytes(pdfUrl);
        if (cancelled) return;
        const pdf = await getDocument({ data: bytes }).promise;
        if (cancelled) {
          await pdf.destroy();
          return;
        }
        const sizes: PageSize[] = [];
        for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
          const page = await pdf.getPage(pageNumber);
          const viewport = page.getViewport({ scale: 1 });
          sizes.push({ width: viewport.width, height: viewport.height });
        }
        if (cancelled) {
          await pdf.destroy();
          return;
        }
        loadedDoc = pdf;
        setPageSizes(sizes);
        setDoc(pdf);
      } catch (error) {
        if (!cancelled) {
          setLoadError(
            error instanceof Error ? error.message : "Could not load the template PDF.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (loadedDoc) {
        void loadedDoc.destroy();
      }
    };
  }, [pdfUrl]);

  const selected = useMemo(
    () => value.find((item) => item.id === selectedId) ?? null,
    [selectedId, value],
  );

  function updateField(id: string, patch: Partial<TemplateFieldLayoutItem>) {
    onChange(value.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function removeField(id: string) {
    onChange(value.filter((item) => item.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  function placeField(
    type: TemplateFieldType,
    role: TemplateFieldRole,
    page: number,
    pdfX: number,
    pdfY: number,
  ) {
    if (readOnly) return;
    const resolvedRole: TemplateFieldRole =
      SIGNING_ONLY_TYPES.has(type) && !HUMAN_SIGNER_ROLES.has(role) ? "Agent" : role;
    const size = DEFAULT_SIZE[type];
    const pageSize = pageSizes[page - 1];
    if (!pageSize) return;
    const w = size.w;
    const h = size.h;
    const x = Math.max(0, Math.min(pdfX - w / 2, pageSize.width - w));
    const y = Math.max(0, Math.min(pdfY - h / 2, pageSize.height - h));
    const next: TemplateFieldLayoutItem = {
      id: newId(),
      name: uniqueName(defaultName(type, resolvedRole), value),
      type,
      role: resolvedRole,
      page,
      x: Math.round(x * 1000) / 1000,
      y: Math.round(y * 1000) / 1000,
      w,
      h,
    };
    onChange([...value, next]);
    setSelectedId(next.id);
    setArmedType(null);
  }

  function onFieldPointerDown(
    event: ReactPointerEvent<HTMLButtonElement>,
    field: TemplateFieldLayoutItem,
    mode: "move" | "resize",
  ) {
    if (readOnly) return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedId(field.id);
    setArmedType(null);
    dragRef.current = {
      id: field.id,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      orig: { ...field },
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onFieldPointerMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    const pageEl = event.currentTarget.closest("[data-page]") as HTMLElement | null;
    if (!pageEl) return;
    const rect = pageEl.getBoundingClientRect();
    const scaleX = (pageSizes[drag.orig.page - 1]?.width ?? rect.width) / rect.width;
    const scaleY = (pageSizes[drag.orig.page - 1]?.height ?? rect.height) / rect.height;
    const dx = (event.clientX - drag.startX) * scaleX;
    const dy = (event.clientY - drag.startY) * scaleY;
    const pageSize = pageSizes[drag.orig.page - 1];
    if (!pageSize) return;

    if (drag.mode === "move") {
      const x = Math.max(0, Math.min(drag.orig.x + dx, pageSize.width - drag.orig.w));
      const y = Math.max(0, Math.min(drag.orig.y + dy, pageSize.height - drag.orig.h));
      updateField(drag.id, {
        x: Math.round(x * 1000) / 1000,
        y: Math.round(y * 1000) / 1000,
      });
      return;
    }

    const w = Math.max(16, Math.min(drag.orig.w + dx, pageSize.width - drag.orig.x));
    const h = Math.max(16, Math.min(drag.orig.h + dy, pageSize.height - drag.orig.y));
    updateField(drag.id, {
      w: Math.round(w * 1000) / 1000,
      h: Math.round(h * 1000) / 1000,
    });
  }

  function onFieldPointerUp(event: ReactPointerEvent<HTMLButtonElement>) {
    if (!dragRef.current) return;
    dragRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // already released
    }
  }

  return (
    <div
      className={cn(
        "border-border bg-muted/20 grid min-h-[28rem] gap-0 overflow-hidden rounded-lg border lg:max-h-[52rem] lg:min-h-[36rem] lg:h-[min(72vh,52rem)] lg:grid-cols-[14rem_minmax(0,1fr)_16rem] lg:grid-rows-1",
        className,
      )}
    >
      <aside className="border-border grid max-h-[50vh] gap-4 overflow-y-auto border-b p-4 lg:max-h-none lg:min-h-0 lg:border-r lg:border-b-0">
        <div className="grid gap-2">
          <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
            Signer role
          </p>
          <div className="bg-background grid grid-cols-3 gap-1 rounded-md border p-1">
            {(["Prefill", "Company", "Agent"] as const).map((role) => (
              <Button
                key={role}
                type="button"
                size="sm"
                variant={placeRole === role ? "default" : "ghost"}
                disabled={readOnly}
                onClick={() => setPlaceRoleSafe(role)}
              >
                {role}
              </Button>
            ))}
          </div>
          <p className="text-muted-foreground text-xs">
            Prefill = commercial text the Hub fills. Company = named officer signs
            first. Agent = recipient signs second. Org seal still finalizes the PDF.
          </p>
        </div>

        <div className="border-border bg-background/80 grid gap-2 rounded-md border p-3">
          <p className="text-foreground text-xs font-semibold">Signing workflow</p>
          <ol className="text-muted-foreground list-decimal space-y-1 pl-4 text-xs leading-5">
            <li>Select Prefill, place Text (or Date / Checkbox) fields.</li>
            <li>Select Company, place Signature and Date for the officer.</li>
            <li>Select Agent, place Signature and Date for the recipient.</li>
            <li>Save fields, map Prefill sources, then preview and publish.</li>
          </ol>
        </div>

        <div className="grid gap-2">
          <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
            Fields
          </p>
          <div className="grid gap-2">
            {PALETTE.filter((item) => item.roles.includes(placeRole)).map((item) => {
              const Icon = item.icon;
              const armed = armedType === item.type;
              return (
                <button
                  key={item.type}
                  type="button"
                  draggable={!readOnly}
                  disabled={readOnly}
                  onDragStart={(event) => {
                    event.dataTransfer.setData(DND_MIME, item.type);
                    event.dataTransfer.effectAllowed = "copy";
                  }}
                  onClick={() =>
                    setArmedType((current) =>
                      current === item.type ? null : item.type,
                    )
                  }
                  className={cn(
                    "bg-background hover:border-primary/50 flex items-start gap-3 rounded-md border px-3 py-2 text-left transition-colors",
                    armed ? "border-primary ring-ring ring-2" : "border-border",
                    readOnly ? "opacity-60" : "cursor-grab active:cursor-grabbing",
                  )}
                >
                  <Icon className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{item.label}</span>
                    <span className="text-muted-foreground block text-xs">
                      {item.hint}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-muted-foreground text-xs">
            Drag onto the page, or click a field then click the PDF.
            {placeRole === "Prefill"
              ? " Signature and initials appear only under Agent."
              : null}
          </p>
        </div>

        {!readOnly && onSave ? (
          <Button type="button" onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save fields"}
          </Button>
        ) : null}
      </aside>

      <div
        ref={viewerRef}
        className="bg-background min-h-0 overflow-x-auto overflow-y-auto p-4 lg:max-h-none"
      >
        {loadError ? (
          <p className="text-destructive text-sm">{loadError}</p>
        ) : loading || !doc ? (
          <p className="text-muted-foreground text-sm">Loading PDF…</p>
        ) : (
          <div className="mx-auto grid w-full max-w-4xl gap-8 pb-4">
            <p className="text-muted-foreground sticky top-0 z-10 bg-background/95 py-1 text-xs backdrop-blur-sm">
              {doc.numPages} page{doc.numPages === 1 ? "" : "s"} — scroll inside this
              panel to review the full document.
            </p>
            {armedType ? (
              <p className="bg-primary/10 text-primary rounded-md px-3 py-2 text-sm">
                Click the document to place a {armedType} field for {placeRole}.
              </p>
            ) : null}
            {pageSizes.map((size, index) => {
              const page = index + 1;
              return (
                <PdfPageCanvas
                  key={page}
                  doc={doc}
                  pageNumber={page}
                  pageWidth={size.width}
                  pageHeight={size.height}
                  viewerWidth={viewerWidth}
                  fields={value.filter((item) => item.page === page)}
                  selectedId={selectedId}
                  armedType={armedType}
                  placeRole={placeRole}
                  readOnly={readOnly}
                  onPlace={(type, role, x, y) => placeField(type, role, page, x, y)}
                  onSelect={setSelectedId}
                  onFieldPointerDown={onFieldPointerDown}
                  onFieldPointerMove={onFieldPointerMove}
                  onFieldPointerUp={onFieldPointerUp}
                />
              );
            })}
          </div>
        )}
      </div>

      <aside className="border-border grid max-h-[50vh] content-start gap-4 overflow-y-auto border-t p-4 lg:max-h-none lg:min-h-0 lg:border-t-0 lg:border-l">
        <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
          Field settings
        </p>
        {selected ? (
          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label htmlFor={`${labelId}-name`}>Name</Label>
              <Input
                id={`${labelId}-name`}
                value={selected.name}
                disabled={readOnly}
                onChange={(event) =>
                  updateField(selected.id, { name: event.target.value })
                }
              />
            </div>
            <div className="grid gap-2">
              <Label>Type</Label>
              <Input value={selected.type} disabled />
            </div>
            <div className="grid gap-2">
              <Label htmlFor={`${labelId}-role`}>Role</Label>
              <Select
                value={selected.role}
                disabled={readOnly}
                onValueChange={(next) => {
                  const role = next as TemplateFieldRole;
                  if (role === "Prefill" && SIGNING_ONLY_TYPES.has(selected.type)) {
                    return;
                  }
                  updateField(selected.id, { role });
                }}
              >
                <SelectTrigger id={`${labelId}-role`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    value="Prefill"
                    disabled={SIGNING_ONLY_TYPES.has(selected.type)}
                  >
                    Prefill
                  </SelectItem>
                  <SelectItem value="Company">Company</SelectItem>
                  <SelectItem value="Agent">Agent</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-muted-foreground text-xs">
              Page {selected.page} · {Math.round(selected.w)}×{Math.round(selected.h)}
            </p>
            {SIGNING_ONLY_TYPES.has(selected.type) ? (
              <p className="text-muted-foreground text-xs leading-5">
                Left blank until that party signs. Company signs first (named officer);
                Agent signs second on My Contract. Org seal finalizes.
              </p>
            ) : null}
            {selected.role === "Prefill" && !SIGNING_ONLY_TYPES.has(selected.type) ? (
              <p className="text-muted-foreground text-xs leading-5">
                Map <strong className="text-foreground">{selected.name}</strong> in
                Draft workspace → Prefill mapping (for example{" "}
                <code className="text-foreground">party.legalFirstName</code>), then
                Save draft. Preview uses sample hub data.
              </p>
            ) : null}
            {selected.role === "Prefill" && SIGNING_ONLY_TYPES.has(selected.type) ? (
              <p className="text-destructive text-xs leading-5">
                Switch this field to Agent (or delete it). Prefill cannot stamp a
                signature or initials.
              </p>
            ) : null}
            {!readOnly ? (
              <Button
                type="button"
                variant="destructive"
                onClick={() => removeField(selected.id)}
              >
                <Trash2 className="size-4" aria-hidden />
                Delete field
              </Button>
            ) : null}
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            Select a placed field to rename it, change role, or delete it.
          </p>
        )}

        <div className="border-border grid gap-2 border-t pt-4">
          <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
            On this document
          </p>
          {value.length === 0 ? (
            <p className="text-muted-foreground text-sm">No fields yet.</p>
          ) : (
            <ul className="grid gap-1">
              {value.map((field) => (
                <li key={field.id}>
                  <button
                    type="button"
                    className={cn(
                      "hover:bg-muted w-full rounded-md px-2 py-1.5 text-left text-sm",
                      field.id === selectedId ? "bg-muted font-medium" : null,
                    )}
                    onClick={() => setSelectedId(field.id)}
                  >
                    <span className="block truncate">{field.name}</span>
                    <span className="text-muted-foreground text-xs">
                      {field.role} · {field.type} · p{field.page}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}

type PdfPageCanvasProps = {
  doc: PDFDocumentProxy;
  pageNumber: number;
  pageWidth: number;
  pageHeight: number;
  viewerWidth: number;
  fields: TemplateFieldLayoutItem[];
  selectedId: string | null;
  armedType: TemplateFieldType | null;
  placeRole: TemplateFieldRole;
  readOnly: boolean;
  onPlace: (
    type: TemplateFieldType,
    role: TemplateFieldRole,
    x: number,
    y: number,
  ) => void;
  onSelect: (id: string) => void;
  onFieldPointerDown: (
    event: ReactPointerEvent<HTMLButtonElement>,
    field: TemplateFieldLayoutItem,
    mode: "move" | "resize",
  ) => void;
  onFieldPointerMove: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onFieldPointerUp: (event: ReactPointerEvent<HTMLButtonElement>) => void;
};

function PdfPageCanvas({
  doc,
  pageNumber,
  pageWidth,
  pageHeight,
  viewerWidth,
  fields,
  selectedId,
  armedType,
  placeRole,
  readOnly,
  onPlace,
  onSelect,
  onFieldPointerDown,
  onFieldPointerMove,
  onFieldPointerUp,
}: PdfPageCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const displayWidth = Math.min(Math.max(viewerWidth - 32, 320), pageWidth);
  const scale = displayWidth / pageWidth;
  const displayHeight = pageHeight * scale;

  useEffect(() => {
    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<void> } | null = null;
    setRenderError(null);
    void (async () => {
      try {
        const page = await doc.getPage(pageNumber);
        if (cancelled) return;
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        if (!canvas) return;
        const context = canvas.getContext("2d");
        if (!context) return;
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${displayWidth}px`;
        canvas.style.height = `${displayHeight}px`;
        renderTask = page.render({ canvasContext: context, viewport });
        if (cancelled) {
          renderTask.cancel();
          return;
        }
        await renderTask.promise;
      } catch {
        if (!cancelled) {
          setRenderError("Could not render this page.");
        }
      }
    })();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [doc, pageNumber, scale, displayWidth, displayHeight]);

  function eventToPdfPoint(
    event: { clientX: number; clientY: number },
    el: HTMLElement,
  ) {
    const rect = el.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * pageWidth,
      y: ((event.clientY - rect.top) / rect.height) * pageHeight,
    };
  }

  function onDrop(event: ReactDragEvent<HTMLDivElement>) {
    if (readOnly) return;
    event.preventDefault();
    const type = event.dataTransfer.getData(DND_MIME) as TemplateFieldType;
    if (!type || !DEFAULT_SIZE[type]) return;
    const point = eventToPdfPoint(event, event.currentTarget);
    onPlace(type, placeRole, point.x, point.y);
  }

  return (
    <div className="grid gap-2">
      <p className="text-muted-foreground text-xs font-medium">Page {pageNumber}</p>
      {renderError ? <p className="text-destructive text-sm">{renderError}</p> : null}
      <div
        data-page={pageNumber}
        role="application"
        aria-label={`PDF page ${pageNumber} drop target`}
        className={cn(
          "relative mx-auto overflow-hidden rounded-md border bg-card shadow-sm",
          armedType ? "ring-primary/40 cursor-crosshair ring-2" : null,
        )}
        style={{ width: displayWidth, height: displayHeight }}
        onDragOver={(event) => {
          if (readOnly) return;
          if ([...event.dataTransfer.types].includes(DND_MIME)) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }
        }}
        onDrop={onDrop}
      >
        <canvas ref={canvasRef} className="block" aria-hidden />
        {armedType && !readOnly ? (
          <button
            type="button"
            className="absolute inset-0 z-10 cursor-crosshair bg-transparent"
            aria-label={`Place ${armedType} on page ${pageNumber}`}
            onClick={(event) => {
              const point = eventToPdfPoint(event, event.currentTarget);
              onPlace(armedType, placeRole, point.x, point.y);
            }}
          />
        ) : null}
        {fields.map((field) => {
          const selected = field.id === selectedId;
          const meta = PALETTE.find((item) => item.type === field.type);
          const Icon = meta?.icon ?? Type;
          return (
            <button
              key={field.id}
              type="button"
              className={cn(
                "absolute z-20 flex items-stretch overflow-hidden rounded-sm border text-left text-micro leading-tight shadow-sm",
                field.role === "Agent"
                  ? "border-primary bg-primary/15 text-foreground"
                  : field.role === "Company"
                    ? "border-chart-2 bg-chart-2/15 text-foreground"
                    : "border-accent-foreground/30 bg-accent/50 text-foreground",
                selected ? "ring-ring z-30 ring-2" : null,
              )}
              style={{
                left: `${(field.x / pageWidth) * 100}%`,
                top: `${(field.y / pageHeight) * 100}%`,
                width: `${(field.w / pageWidth) * 100}%`,
                height: `${(field.h / pageHeight) * 100}%`,
              }}
              onClick={(event) => {
                event.stopPropagation();
                onSelect(field.id);
              }}
              onPointerDown={(event) => onFieldPointerDown(event, field, "move")}
              onPointerMove={onFieldPointerMove}
              onPointerUp={onFieldPointerUp}
            >
              <span className="bg-background/70 flex items-center px-1">
                <Icon className="size-3 shrink-0" aria-hidden />
              </span>
              <span className="block min-w-0 flex-1 truncate px-1 py-0.5 font-medium">
                {field.name}
              </span>
              {!readOnly && selected ? (
                <span
                  className="bg-primary absolute right-0 bottom-0 size-2.5 cursor-se-resize"
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    onFieldPointerDown(
                      event as unknown as ReactPointerEvent<HTMLButtonElement>,
                      field,
                      "resize",
                    );
                  }}
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
