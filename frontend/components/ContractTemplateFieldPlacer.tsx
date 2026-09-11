import {
  Calendar,
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  FileWarning,
  Maximize2,
  Minus,
  PenLine,
  Plus,
  Signature,
  Trash2,
  Type,
} from "lucide-react";
import {
  GlobalWorkerOptions,
  getDocument,
  type PDFDocumentProxy,
  type RenderTask,
} from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  type DragEvent as ReactDragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
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
import { Skeleton } from "@/components/ui/skeleton";
import { loadProtectedPdfBytes } from "@/lib/protected-pdf";
import { cn } from "@/lib/utils";

GlobalWorkerOptions.workerSrc = pdfWorker;

export type TemplateFieldType = "text" | "signature" | "date" | "initials" | "checkbox";

export type TemplateFieldRole = "Prefill" | "Company" | "Agent";

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
    roles: ["Company", "Agent"],
  },
  {
    type: "initials",
    label: "Initials",
    icon: PenLine,
    hint: "Drawn at signing",
    roles: ["Company", "Agent"],
  },
  {
    type: "date",
    label: "Date",
    icon: Calendar,
    hint: "Signed-on or commercial date",
    roles: ["Prefill", "Company", "Agent"],
  },
  {
    type: "text",
    label: "Text",
    icon: Type,
    hint: "Fillable text",
    roles: ["Prefill", "Company", "Agent"],
  },
  {
    type: "checkbox",
    label: "Checkbox",
    icon: CheckSquare,
    hint: "Yes / no",
    roles: ["Prefill", "Company", "Agent"],
  },
];

const SIGNING_ONLY_TYPES = new Set<TemplateFieldType>(["signature", "initials"]);
const HUMAN_SIGNER_ROLES = new Set<TemplateFieldRole>(["Company", "Agent"]);

const DEFAULT_SIZE: Record<TemplateFieldType, { w: number; h: number }> = {
  text: { w: 180, h: 28 },
  signature: { w: 200, h: 56 },
  date: { w: 140, h: 28 },
  initials: { w: 80, h: 40 },
  checkbox: { w: 22, h: 22 },
};

/**
 * Role is the one thing about a placed box that changes who fills it, so it is
 * carried by hue *and* by an explicit word on every chip, in the legend, and in
 * the inspector. Neither tone is gold: on this page gold means "press this",
 * and a document covered in gold boxes would leave the Save control with no
 * colour of its own.
 */
const ROLE_STYLES: Record<
  TemplateFieldRole,
  { box: string; dot: string; chip: string; blurb: string }
> = {
  Prefill: {
    box: "border-info bg-chip-info text-info",
    dot: "bg-info",
    chip: "border-chip-info-edge bg-chip-info text-info",
    blurb: "The Hub writes office, agent, and commercial terms into these.",
  },
  Company: {
    box: "border-role-company-ink bg-chip-role-company text-role-company-ink",
    dot: "bg-role-company-ink",
    chip: "border-chip-role-company-edge bg-chip-role-company text-role-company-ink",
    blurb: "The named company officer completes these before the agent signs.",
  },
  Agent: {
    box: "border-role-protected-ink bg-chip-role-protected text-role-protected-ink",
    dot: "bg-role-protected-ink",
    chip: "border-chip-role-protected-edge bg-chip-role-protected text-role-protected-ink",
    blurb: "The agent completes these at signing — signature, initials, date.",
  },
};

const DND_MIME = "application/x-onest-field-type";

const ZOOM_MIN = 0.4;
const ZOOM_MAX = 2.5;
const ZOOM_STEP = 0.2;

/** One PDF point per press, ten with Shift — the same ladder a design tool uses. */
const NUDGE_SMALL = 1;
const NUDGE_LARGE = 10;

type PageSize = { width: number; height: number };

type ContractTemplateFieldPlacerProps = {
  pdfUrl: string;
  value: TemplateFieldLayoutItem[];
  onChange: (next: TemplateFieldLayoutItem[]) => void;
  readOnly?: boolean;
  className?: string;
  onSave?: () => void;
  saving?: boolean;
  /** Layout differs from the saved one — colours the Save control. */
  dirty?: boolean;
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

function round(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, max));
}

export function ContractTemplateFieldPlacer({
  pdfUrl,
  value,
  onChange,
  readOnly = false,
  className,
  onSave,
  saving = false,
  dirty = false,
}: ContractTemplateFieldPlacerProps) {
  const labelId = useId();
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef(new Map<number, HTMLDivElement>());
  const [viewerWidth, setViewerWidth] = useState(900);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pageSizes, setPageSizes] = useState<PageSize[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [placeRole, setPlaceRole] = useState<TemplateFieldRole>("Prefill");
  const [armedType, setArmedType] = useState<TemplateFieldType | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [fitToWidth, setFitToWidth] = useState(true);
  const [zoom, setZoom] = useState(1);
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

  const widestPage = useMemo(
    () => pageSizes.reduce((widest, size) => Math.max(widest, size.width), 612),
    [pageSizes],
  );

  /**
   * Fit is the default because a contract is a reading task before it is a
   * placement task: the first thing a reviewer does is read the clause the box
   * has to land beside.
   */
  const fitScale = useMemo(
    () => clamp((viewerWidth - 56) / widestPage, ZOOM_MIN, ZOOM_MAX),
    [viewerWidth, widestPage],
  );
  const scale = fitToWidth ? fitScale : zoom;

  function applyZoom(next: number) {
    setZoom(clamp(round(next), ZOOM_MIN, ZOOM_MAX));
    setFitToWidth(false);
  }

  /**
   * Which page the reader is looking at, so the toolbar counter is a readout
   * rather than a second, disagreeing source of truth.
   */
  useEffect(() => {
    const root = viewerRef.current;
    if (!root || pageSizes.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        const page = Number((visible.target as HTMLElement).dataset.pageWrapper);
        if (page) setCurrentPage(page);
      },
      { root, threshold: [0.1, 0.5, 0.9] },
    );
    for (const node of pageRefs.current.values()) observer.observe(node);
    return () => observer.disconnect();
  }, [pageSizes.length]);

  const goToPage = useCallback((page: number) => {
    const node = pageRefs.current.get(page);
    if (!node) return;
    setCurrentPage(page);
    node.scrollIntoView({ block: "start", behavior: "smooth" });
  }, []);

  const selected = useMemo(
    () => value.find((item) => item.id === selectedId) ?? null,
    [selectedId, value],
  );

  const grouped = useMemo(() => {
    const byPage = new Map<number, TemplateFieldLayoutItem[]>();
    for (const field of value) {
      const bucket = byPage.get(field.page);
      if (bucket) bucket.push(field);
      else byPage.set(field.page, [field]);
    }
    return [...byPage.entries()].sort((a, b) => a[0] - b[0]);
  }, [value]);

  const agentFieldCount = value.filter((field) => field.role === "Agent").length;

  function updateField(id: string, patch: Partial<TemplateFieldLayoutItem>) {
    onChange(value.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function removeField(id: string) {
    onChange(value.filter((item) => item.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  function selectField(id: string) {
    setSelectedId(id);
    const field = value.find((item) => item.id === id);
    if (field) goToPage(field.page);
  }

  function placeField(
    type: TemplateFieldType,
    role: TemplateFieldRole,
    page: number,
    pdfX: number,
    pdfY: number,
  ) {
    if (readOnly) return;
    const resolvedRole =
      SIGNING_ONLY_TYPES.has(type) && !HUMAN_SIGNER_ROLES.has(role) ? "Agent" : role;
    const size = DEFAULT_SIZE[type];
    const pageSize = pageSizes[page - 1];
    if (!pageSize) return;
    const { w, h } = size;
    const next: TemplateFieldLayoutItem = {
      id: newId(),
      name: uniqueName(defaultName(type, resolvedRole), value),
      type,
      role: resolvedRole,
      page,
      x: round(clamp(pdfX - w / 2, 0, pageSize.width - w)),
      y: round(clamp(pdfY - h / 2, 0, pageSize.height - h)),
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
    // Safari does not focus a button on pointer down, and without focus the
    // arrow-key nudge below never receives a key event.
    event.currentTarget.focus();
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
    const pageSize = pageSizes[drag.orig.page - 1];
    if (!pageSize) return;
    const scaleX = pageSize.width / rect.width;
    const scaleY = pageSize.height / rect.height;
    const dx = (event.clientX - drag.startX) * scaleX;
    const dy = (event.clientY - drag.startY) * scaleY;

    if (drag.mode === "move") {
      updateField(drag.id, {
        x: round(clamp(drag.orig.x + dx, 0, pageSize.width - drag.orig.w)),
        y: round(clamp(drag.orig.y + dy, 0, pageSize.height - drag.orig.h)),
      });
      return;
    }

    updateField(drag.id, {
      w: round(clamp(drag.orig.w + dx, 16, pageSize.width - drag.orig.x)),
      h: round(clamp(drag.orig.h + dy, 16, pageSize.height - drag.orig.y)),
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

  /**
   * Keyboard parity for the two things dragging does. A placement tool whose
   * only move is a pointer drag is unusable with a keyboard, and this one has
   * to survive an accessibility review as an administrative surface.
   */
  function onWorkbenchKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      setArmedType(null);
      setSelectedId(null);
      return;
    }
    if (!selected || readOnly) return;
    const target = event.target as HTMLElement;
    if (target.closest("input, textarea, select, [role='combobox']")) return;

    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      removeField(selected.id);
      return;
    }

    const step = event.shiftKey ? NUDGE_LARGE : NUDGE_SMALL;
    const delta =
      event.key === "ArrowLeft"
        ? { x: -step, y: 0 }
        : event.key === "ArrowRight"
          ? { x: step, y: 0 }
          : event.key === "ArrowUp"
            ? { x: 0, y: -step }
            : event.key === "ArrowDown"
              ? { x: 0, y: step }
              : null;
    if (!delta) return;
    const pageSize = pageSizes[selected.page - 1];
    if (!pageSize) return;
    event.preventDefault();
    updateField(selected.id, {
      x: round(clamp(selected.x + delta.x, 0, pageSize.width - selected.w)),
      y: round(clamp(selected.y + delta.y, 0, pageSize.height - selected.h)),
    });
  }

  const pageCount = pageSizes.length;
  const pageNumbers = useMemo(
    () => pageSizes.map((_size, index) => index + 1),
    [pageSizes],
  );

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: delegation root for the focusable field buttons inside, not a control itself.
    <div
      onKeyDown={onWorkbenchKeyDown}
      className={cn(
        "border-border bg-card grid overflow-hidden rounded-(--radius-card) border",
        "lg:h-[calc(100dvh-25rem)] lg:max-h-[58rem] lg:min-h-[26rem]",
        "lg:grid-cols-[13.5rem_minmax(0,1fr)_18rem] lg:grid-rows-[auto_minmax(0,1fr)]",
        className,
      )}
    >
      <PlacerToolbar
        currentPage={currentPage}
        pageCount={pageCount}
        onGoToPage={goToPage}
        scale={scale}
        fitToWidth={fitToWidth}
        onZoomIn={() => applyZoom(scale + ZOOM_STEP)}
        onZoomOut={() => applyZoom(scale - ZOOM_STEP)}
        onFit={() => setFitToWidth(true)}
        fieldCount={value.length}
        agentFieldCount={agentFieldCount}
        dirty={dirty}
        saving={saving}
        onSave={!readOnly ? onSave : undefined}
      />

      <aside
        aria-label="Field palette"
        className="border-border grid max-h-[45vh] content-start gap-6 overflow-y-auto border-b p-5 lg:max-h-none lg:min-h-0 lg:border-r lg:border-b-0"
      >
        <fieldset className="grid gap-2">
          <legend className="text-muted-foreground mb-2 text-xs font-semibold">
            Place fields for
          </legend>
          <div className="bg-background border-border grid grid-cols-3 gap-1 rounded-md border p-1">
            {(["Prefill", "Company", "Agent"] as const).map((role) => (
              <button
                key={role}
                type="button"
                aria-pressed={placeRole === role}
                disabled={readOnly}
                onClick={() => setPlaceRoleSafe(role)}
                className={cn(
                  "focus-visible:ring-ring rounded-sm px-2 py-1.5 text-sm font-medium transition-colors duration-(--motion-fast) focus-visible:ring-3 focus-visible:outline-none disabled:opacity-50",
                  placeRole === role
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted",
                )}
              >
                {role}
              </button>
            ))}
          </div>
          <p className="text-muted-foreground flex items-start gap-2 text-xs leading-5">
            <span
              className={cn(
                "mt-1 size-2 shrink-0 rounded-full",
                ROLE_STYLES[placeRole].dot,
              )}
              aria-hidden
            />
            {ROLE_STYLES[placeRole].blurb}
          </p>
        </fieldset>

        <div className="grid gap-2">
          <p className="text-muted-foreground text-xs font-semibold">Fields</p>
          <div className="grid gap-1.5">
            {PALETTE.filter((item) => item.roles.includes(placeRole)).map((item) => {
              const Icon = item.icon;
              const armed = armedType === item.type;
              return (
                <button
                  key={item.type}
                  type="button"
                  draggable={!readOnly}
                  disabled={readOnly}
                  aria-pressed={armed}
                  onDragStart={(event) => {
                    event.dataTransfer.setData(DND_MIME, item.type);
                    event.dataTransfer.effectAllowed = "copy";
                    setArmedType(null);
                  }}
                  onClick={() =>
                    setArmedType((current) =>
                      current === item.type ? null : item.type,
                    )
                  }
                  className={cn(
                    "bg-background focus-visible:ring-ring flex items-center gap-2.5 rounded-md border px-2.5 py-2 text-left transition-[background-color,border-color] duration-(--motion-fast) focus-visible:ring-3 focus-visible:outline-none",
                    armed
                      ? "border-ring bg-accent"
                      : "border-border hover:border-border-strong hover:bg-accent/40",
                    readOnly ? "opacity-60" : "cursor-grab active:cursor-grabbing",
                  )}
                >
                  <span
                    className={cn(
                      "grid size-7 shrink-0 place-items-center rounded-sm border",
                      ROLE_STYLES[placeRole].chip,
                    )}
                  >
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {item.label}
                    </span>
                    <span className="text-muted-foreground block truncate text-xs">
                      {item.hint}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <p className="text-muted-foreground border-border border-t pt-5 text-xs leading-5">
          Drag a field onto the page, or select one and click where it goes. Arrow keys
          nudge a placed field, <kbd className="font-sans">Shift</kbd> nudges by ten,{" "}
          <kbd className="font-sans">Delete</kbd> removes it.
        </p>
      </aside>

      <div
        ref={viewerRef}
        className="bg-muted/35 relative max-h-[70vh] min-h-[20rem] overflow-auto p-6 lg:max-h-none lg:min-h-0"
      >
        {armedType && !readOnly ? (
          <p
            role="status"
            className="border-ring bg-card text-foreground shadow-popover sticky top-0 z-30 mx-auto mb-4 w-fit rounded-md border px-3 py-1.5 text-sm"
          >
            Click the page to place a <span className="font-semibold">{armedType}</span>{" "}
            field for <span className="font-semibold">{placeRole}</span>.
          </p>
        ) : null}

        {loadError ? (
          <div className="grid h-full place-items-center">
            <div className="max-w-measure text-center">
              <FileWarning
                className="text-muted-foreground mx-auto size-6"
                aria-hidden
              />
              <p className="mt-2 text-sm font-semibold">Could not open this PDF</p>
              <p className="text-muted-foreground mt-1 text-sm">{loadError}</p>
            </div>
          </div>
        ) : loading || !doc ? (
          <div className="mx-auto grid w-full max-w-4xl gap-3" aria-busy>
            <Skeleton className="h-4 w-32" />
            <Skeleton className="aspect-[8.5/11] w-full" />
            <span className="sr-only">Loading the template PDF</span>
          </div>
        ) : (
          <div className="mx-auto grid w-fit min-w-full justify-items-center gap-6 pb-2">
            {pageSizes.map((size, index) => {
              const page = index + 1;
              return (
                <PdfPageCanvas
                  key={page}
                  ref={(node) => {
                    if (node) pageRefs.current.set(page, node);
                    else pageRefs.current.delete(page);
                  }}
                  doc={doc}
                  pageNumber={page}
                  pageWidth={size.width}
                  pageHeight={size.height}
                  scale={scale}
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

      <aside
        aria-label="Field inspector"
        className="border-border grid max-h-[55vh] content-start gap-5 overflow-y-auto border-t p-5 lg:max-h-none lg:min-h-0 lg:border-t-0 lg:border-l"
      >
        {selected ? (
          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor={`${labelId}-name`}>Name</Label>
              <Input
                id={`${labelId}-name`}
                value={selected.name}
                disabled={readOnly}
                className="bg-background font-mono text-xs"
                onChange={(event) =>
                  updateField(selected.id, { name: event.target.value })
                }
              />
            </div>
            <div className="grid gap-1.5">
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
                <SelectTrigger id={`${labelId}-role`} className="bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    value="Prefill"
                    disabled={SIGNING_ONLY_TYPES.has(selected.type)}
                  >
                    Prefill — the Hub fills it
                  </SelectItem>
                  <SelectItem value="Company">Company — officer signs first</SelectItem>
                  <SelectItem value="Agent">Agent — signed at signing</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${labelId}-page`}>Page</Label>
              <Select
                value={String(selected.page)}
                disabled={readOnly || pageCount < 2}
                onValueChange={(next) => {
                  updateField(selected.id, { page: Number(next) });
                  goToPage(Number(next));
                }}
              >
                <SelectTrigger id={`${labelId}-page`} className="bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {pageNumbers.map((page) => (
                    <SelectItem key={page} value={String(page)}>
                      Page {page}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Typed coordinates, so exact placement never depends on a steady
                hand — and so a keyboard user can do everything a mouse can. */}
            <fieldset className="grid gap-1.5">
              <legend className="text-muted-foreground text-xs font-semibold">
                Position on the page (PDF points)
              </legend>
              <div className="grid grid-cols-2 gap-2">
                {(
                  [
                    { key: "x", label: "X" },
                    { key: "y", label: "Y" },
                    { key: "w", label: "Width" },
                    { key: "h", label: "Height" },
                  ] as const
                ).map((axis) => (
                  <div key={axis.key} className="grid gap-1">
                    <Label
                      htmlFor={`${labelId}-${axis.key}`}
                      className="text-muted-foreground text-micro"
                    >
                      {axis.label}
                    </Label>
                    <Input
                      id={`${labelId}-${axis.key}`}
                      type="number"
                      inputMode="decimal"
                      className="bg-background h-8 tabular-nums"
                      disabled={readOnly}
                      value={Math.round(selected[axis.key])}
                      onChange={(event) => {
                        const next = Number(event.target.value);
                        if (Number.isNaN(next)) return;
                        const pageSize = pageSizes[selected.page - 1];
                        if (!pageSize) return;
                        const limit =
                          axis.key === "x"
                            ? pageSize.width - selected.w
                            : axis.key === "y"
                              ? pageSize.height - selected.h
                              : axis.key === "w"
                                ? pageSize.width - selected.x
                                : pageSize.height - selected.y;
                        const floor = axis.key === "w" || axis.key === "h" ? 16 : 0;
                        updateField(selected.id, {
                          [axis.key]: round(clamp(next, floor, limit)),
                        });
                      }}
                    />
                  </div>
                ))}
              </div>
            </fieldset>

            {SIGNING_ONLY_TYPES.has(selected.type) ? (
              <p className="text-muted-foreground text-xs leading-5">
                Left blank until that party signs. The company officer signs first, then
                the agent. The organization seal finalizes the PDF.
              </p>
            ) : null}

            {selected.role === "Prefill" && !SIGNING_ONLY_TYPES.has(selected.type) ? (
              <p className="text-muted-foreground text-xs leading-5">
                Save the layout, then map{" "}
                <strong className="text-foreground font-mono">{selected.name}</strong>{" "}
                to a hub source on the Data mapping tab.
              </p>
            ) : null}

            {!readOnly ? (
              <Button
                type="button"
                variant="outline"
                className="text-destructive hover:bg-chip-destructive hover:text-destructive"
                onClick={() => removeField(selected.id)}
              >
                <Trash2 className="size-4" aria-hidden />
                Delete field
              </Button>
            ) : null}
          </div>
        ) : (
          <p className="text-muted-foreground text-sm leading-5">
            Select a placed field to rename it, change its role, move it to another
            page, or set exact coordinates.
          </p>
        )}

        <div className="border-border grid gap-2 border-t pt-4">
          <p className="text-muted-foreground flex items-center justify-between text-xs font-semibold">
            <span>On this document</span>
            <span className="tabular-nums">{value.length}</span>
          </p>
          {value.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No fields yet. Drag one from the palette onto the page.
            </p>
          ) : (
            <div className="grid gap-3">
              {grouped.map(([page, fields]) => (
                <div key={page} className="grid gap-1">
                  <p className="text-muted-foreground text-micro font-semibold">
                    Page {page}
                  </p>
                  <ul className="grid gap-0.5">
                    {fields.map((field) => {
                      const meta = PALETTE.find((item) => item.type === field.type);
                      const Icon = meta?.icon ?? Type;
                      return (
                        <li key={field.id}>
                          <button
                            type="button"
                            className={cn(
                              "focus-visible:ring-ring flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors duration-(--motion-fast) focus-visible:ring-3 focus-visible:outline-none",
                              field.id === selectedId
                                ? "bg-accent"
                                : "hover:bg-muted/70",
                            )}
                            onClick={() => selectField(field.id)}
                          >
                            <span
                              className={cn(
                                "grid size-6 shrink-0 place-items-center rounded-sm border",
                                ROLE_STYLES[field.role].chip,
                              )}
                            >
                              <Icon className="size-3" aria-hidden />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-mono text-xs">
                                {field.name}
                              </span>
                              <span className="text-muted-foreground block truncate text-xs">
                                {field.role} · {field.type}
                              </span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

/**
 * Document controls, on one rule above all three panes.
 *
 * Page position and zoom belong to the document rather than to either rail, and
 * Save sits at the end of the same row because the layout is what it saves —
 * previously it was the last item in a scrolling palette, below the fold on a
 * laptop, which is where unsaved work goes to die.
 */
function PlacerToolbar({
  currentPage,
  pageCount,
  onGoToPage,
  scale,
  fitToWidth,
  onZoomIn,
  onZoomOut,
  onFit,
  fieldCount,
  agentFieldCount,
  dirty,
  saving,
  onSave,
}: {
  currentPage: number;
  pageCount: number;
  onGoToPage: (page: number) => void;
  scale: number;
  fitToWidth: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  fieldCount: number;
  agentFieldCount: number;
  dirty: boolean;
  saving: boolean;
  onSave?: () => void;
}) {
  return (
    <div className="border-border bg-card flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-3 py-2 lg:col-span-3">
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8"
          aria-label="Previous page"
          disabled={currentPage <= 1}
          onClick={() => onGoToPage(currentPage - 1)}
        >
          <ChevronLeft className="size-4" aria-hidden />
        </Button>
        <p className="text-sm tabular-nums" aria-live="polite">
          Page <span className="font-semibold">{currentPage}</span>
          <span className="text-muted-foreground"> of {pageCount || "—"}</span>
        </p>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8"
          aria-label="Next page"
          disabled={pageCount === 0 || currentPage >= pageCount}
          onClick={() => onGoToPage(currentPage + 1)}
        >
          <ChevronRight className="size-4" aria-hidden />
        </Button>
      </div>

      <div className="bg-border h-5 w-px" aria-hidden />

      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8"
          aria-label="Zoom out"
          onClick={onZoomOut}
        >
          <Minus className="size-4" aria-hidden />
        </Button>
        <span className="w-12 text-center text-sm tabular-nums">
          {Math.round(scale * 100)}%
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8"
          aria-label="Zoom in"
          onClick={onZoomIn}
        >
          <Plus className="size-4" aria-hidden />
        </Button>
        <Button
          type="button"
          variant={fitToWidth ? "secondary" : "ghost"}
          size="sm"
          className="h-8"
          onClick={onFit}
        >
          <Maximize2 className="size-3.5" aria-hidden />
          Fit
        </Button>
      </div>

      <p className="text-muted-foreground ml-auto hidden text-xs tabular-nums sm:block">
        {fieldCount} field{fieldCount === 1 ? "" : "s"} · {agentFieldCount} for the
        agent
      </p>

      {onSave ? (
        <div className="flex items-center gap-2">
          {dirty ? (
            <span className="text-warning-ink flex items-center gap-1.5 text-xs font-medium">
              <span className="bg-warning size-1.5 rounded-full" aria-hidden />
              Unsaved
            </span>
          ) : null}
          <Button
            type="button"
            size="sm"
            className="h-8"
            variant={dirty ? "default" : "outline"}
            onClick={onSave}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save field layout"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

type PdfPageCanvasProps = {
  ref?: (node: HTMLDivElement | null) => void;
  doc: PDFDocumentProxy;
  pageNumber: number;
  pageWidth: number;
  pageHeight: number;
  scale: number;
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
  ref,
  doc,
  pageNumber,
  pageWidth,
  pageHeight,
  scale,
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
  const displayWidth = Math.round(pageWidth * scale);
  const displayHeight = Math.round(pageHeight * scale);

  useEffect(() => {
    let cancelled = false;
    let task: RenderTask | null = null;
    setRenderError(null);
    void (async () => {
      try {
        const page = await doc.getPage(pageNumber);
        if (cancelled) return;
        // Render at device resolution, present at CSS size. Rendering at CSS
        // pixels left every contract soft on a retina display, which is the
        // one thing a document reviewer notices immediately.
        const ratio = Math.min(globalThis.devicePixelRatio || 1, 2);
        const viewport = page.getViewport({ scale: scale * ratio });
        const canvas = canvasRef.current;
        if (!canvas) return;
        const context = canvas.getContext("2d");
        if (!context) return;
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${displayWidth}px`;
        canvas.style.height = `${displayHeight}px`;
        task = page.render({ canvasContext: context, viewport });
        await task.promise;
      } catch (error) {
        // A cancelled render is the expected outcome of a zoom change, not a
        // failure worth showing the reader.
        if (!cancelled && (error as { name?: string })?.name !== "RenderingCancelled") {
          setRenderError("Could not render this page.");
        }
      }
    })();
    return () => {
      cancelled = true;
      task?.cancel();
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
    <div ref={ref} data-page-wrapper={pageNumber} className="grid w-fit gap-2">
      <p className="text-muted-foreground text-xs">Page {pageNumber}</p>
      {renderError ? <p className="text-destructive text-sm">{renderError}</p> : null}
      <div
        data-page={pageNumber}
        role="application"
        aria-label={`PDF page ${pageNumber} — field placement surface`}
        className={cn(
          "paper-surface border-border bg-card shadow-card relative overflow-hidden rounded-sm border",
          armedType ? "ring-ring cursor-crosshair ring-2" : null,
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
          const compact = field.h * scale < 22;
          return (
            <button
              key={field.id}
              type="button"
              aria-label={`${field.name}, ${field.role} ${field.type} on page ${field.page}`}
              aria-pressed={selected}
              className={cn(
                "text-micro absolute z-20 flex items-stretch overflow-hidden rounded-sm border text-left leading-tight transition-shadow duration-(--motion-fast) focus-visible:outline-none",
                ROLE_STYLES[field.role].box,
                selected
                  ? "ring-ring z-30 shadow-card-hover ring-2"
                  : "hover:shadow-card",
                readOnly ? null : "cursor-move",
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
              {compact ? null : (
                <span className="bg-card/60 flex items-start px-1 pt-0.5">
                  <Icon className="size-3 shrink-0" aria-hidden />
                </span>
              )}
              <span className="block min-w-0 flex-1 truncate px-1 py-0.5 font-medium">
                {field.name}
              </span>
              {!readOnly && selected ? (
                <span
                  className="bg-primary border-card absolute -right-px -bottom-px size-3 cursor-se-resize rounded-tl-sm border"
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
