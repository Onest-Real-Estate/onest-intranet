import { Eraser, PenLine, Type, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type SignatureMode = "draw" | "type";

type ContractSignaturePadProps = {
  className?: string;
  onChange: (dataUrl: string) => void;
};

/** Drawn at the canvas's CSS size; the backing store is this times the DPR. */
const PAD_HEIGHT = 180;
const STROKE_WIDTH = 2.25;

/**
 * The two colours the signature is drawn with, read from `app.css`.
 *
 * They are deliberately theme-invariant — the raster ends up sealed into a
 * legal PDF, so it is ink on paper rather than a themed surface — but they are
 * still tokens, because a literal hex in a component is a bug and a reader
 * should be able to find every colour this product draws in one file.
 */
function signatureColors(element: HTMLElement) {
  const styles = getComputedStyle(element);
  // Keywords, not hex, for the last resort: if the token ever goes missing the
  // fallback must stay legible without becoming a second definition of the
  // colour that quietly outlives a rename in `app.css`.
  return {
    ink: styles.getPropertyValue("--signature-ink").trim() || "black",
    paper: styles.getPropertyValue("--signature-paper").trim() || "white",
  };
}

/**
 * Capture a signature by drawing it or typing it.
 *
 * Typing is not a fallback bolted on for compliance: a trackpad signature is
 * unpleasant on any laptop and impossible with a keyboard alone, so both paths
 * produce the same raster and the choice is a real one. That is also what
 * satisfies "dragging cannot be the only way to complete a task".
 *
 * The pad renders at the device pixel ratio. The previous version kept a fixed
 * 640×180 buffer and stretched it to whatever width the card gave it, so the
 * signature stored in the agreement was upscaled and soft on every retina
 * screen it was drawn on.
 */
export function ContractSignaturePad({
  className,
  onChange,
}: ContractSignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);
  const [mode, setMode] = useState<SignatureMode>("draw");
  const [typed, setTyped] = useState("");
  const typedId = useId();

  /** Repaint the paper at the current size, discarding anything on it. */
  const resetSurface = useCallback((): CanvasRenderingContext2D | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const context = canvas.getContext("2d");
    if (!context) return null;
    const { ink, paper } = signatureColors(canvas);
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || canvas.width;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(PAD_HEIGHT * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.fillStyle = paper;
    context.fillRect(0, 0, width, PAD_HEIGHT);
    context.strokeStyle = ink;
    context.fillStyle = ink;
    context.lineWidth = STROKE_WIDTH;
    context.lineCap = "round";
    context.lineJoin = "round";
    dirty.current = false;
    return context;
  }, []);

  const renderTyped = useCallback(
    (value: string) => {
      const context = resetSurface();
      const canvas = canvasRef.current;
      if (!context || !canvas) return;
      const trimmed = value.trim();
      if (!trimmed) {
        onChange("");
        return;
      }
      const width = canvas.clientWidth || canvas.width;
      // Shrink to fit rather than clipping: a long legal name that runs off the
      // right edge would be sealed into the PDF cut in half.
      let size = 52;
      context.font = `${size}px "Segoe Script", "Brush Script MT", cursive`;
      while (size > 20 && context.measureText(trimmed).width > width - 48) {
        size -= 2;
        context.font = `${size}px "Segoe Script", "Brush Script MT", cursive`;
      }
      context.fillText(trimmed, 24, PAD_HEIGHT / 2 + size / 3);
      dirty.current = true;
      onChange(canvas.toDataURL("image/png"));
    },
    [onChange, resetSurface],
  );

  useEffect(() => {
    resetSurface();
  }, [resetSurface]);

  // The card is responsive, so the buffer has to follow it. Redrawing a typed
  // signature is lossless; a drawn one cannot be rescaled, so it is cleared and
  // the field reports itself empty rather than silently keeping a stale raster.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (mode === "type") {
        renderTyped(typed);
        return;
      }
      const hadInk = dirty.current;
      resetSurface();
      if (hadInk) onChange("");
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [mode, onChange, renderTyped, resetSurface, typed]);

  function clear() {
    resetSurface();
    setTyped("");
    onChange("");
  }

  function switchMode(next: SignatureMode) {
    if (next === mode) return;
    setMode(next);
    clear();
  }

  function pointAt(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  return (
    <div className={cn("grid gap-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        {/*
          A segmented pair, not two primary buttons. The old version filled the
          active mode with brand gold, which put a second gold control on a page
          whose one gold control is "Apply signature and finish" — the page then
          had two answers to "press this". `aria-pressed` is what actually tells
          a screen reader which mode is on; colour alone never did.
        */}
        <fieldset className="border-input bg-muted/40 flex items-center gap-1 rounded-md border p-1">
          <legend className="sr-only">Signature method</legend>
          {(
            [
              { value: "draw", label: "Draw", icon: PenLine },
              { value: "type", label: "Type", icon: Type },
            ] as const
          ).map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={mode === option.value}
              onClick={() => switchMode(option.value)}
              className={cn(
                "focus-visible:ring-ring inline-flex h-7 items-center gap-1.5 rounded-sm px-2.5 text-xs font-semibold transition-colors focus-visible:ring-2 focus-visible:outline-none",
                mode === option.value
                  ? "bg-card text-foreground shadow-card"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <option.icon className="size-3.5" aria-hidden />
              {option.label}
            </button>
          ))}
        </fieldset>
        <Button type="button" size="sm" variant="ghost" onClick={clear}>
          <Eraser className="size-3.5" aria-hidden />
          Clear
        </Button>
      </div>

      {mode === "type" ? (
        <div className="grid gap-2">
          <Label htmlFor={typedId}>Type your full legal name</Label>
          <Input
            id={typedId}
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
              renderTyped(event.target.value);
            }}
            autoComplete="name"
            placeholder="Jordan A. Whitfield"
          />
        </div>
      ) : null}

      <div className="border-input bg-card relative overflow-hidden rounded-md border">
        <canvas
          ref={canvasRef}
          style={{ height: PAD_HEIGHT }}
          className="block w-full touch-none"
          aria-label={
            mode === "draw"
              ? "Signature pad. Drag to sign, or switch to Type to enter your name instead."
              : "Signature preview of your typed name."
          }
          onPointerDown={(event) => {
            if (mode !== "draw") return;
            const context = canvasRef.current?.getContext("2d");
            if (!context) return;
            drawing.current = true;
            const point = pointAt(event);
            context.beginPath();
            context.moveTo(point.x, point.y);
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (!drawing.current || mode !== "draw") return;
            const context = canvasRef.current?.getContext("2d");
            if (!context) return;
            const point = pointAt(event);
            context.lineTo(point.x, point.y);
            context.stroke();
            dirty.current = true;
          }}
          onPointerUp={() => {
            if (!drawing.current) return;
            drawing.current = false;
            const canvas = canvasRef.current;
            if (canvas) onChange(canvas.toDataURL("image/png"));
          }}
        />
        {/*
          The rule and the cross are the one borrowing from paper here: a
          signature block is a line you sign above, and without it the pad is an
          empty rectangle that does not say where to start.
        */}
        <div
          className="pointer-events-none absolute right-6 bottom-9 left-6 flex items-center gap-2"
          aria-hidden
        >
          <X className="text-border-strong size-3.5" />
          <span className="bg-border-strong h-px flex-1" />
        </div>
      </div>

      <p className="text-muted-foreground text-xs">
        {mode === "draw"
          ? "Drag on the line above with a mouse, trackpad, or finger. Prefer a keyboard? Switch to Type."
          : "Your typed name is rendered as the signature stored with the agreement."}
      </p>
    </div>
  );
}
