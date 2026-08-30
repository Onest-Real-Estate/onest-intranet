import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type ContractSignaturePadProps = {
  className?: string;
  onChange: (dataUrl: string) => void;
};

export function ContractSignaturePad({
  className,
  onChange,
}: ContractSignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const [mode, setMode] = useState<"draw" | "type">("draw");
  const [typed, setTyped] = useState("");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#111827";
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
  }, []);

  function emitCanvas() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    onChange(canvas.toDataURL("image/png"));
  }

  function clearCanvas() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    onChange("");
  }

  function pointerPos(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height,
    };
  }

  function renderTyped(value: string) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!value.trim()) {
      onChange("");
      return;
    }
    ctx.fillStyle = "#111827";
    ctx.font = "48px 'Segoe Script', 'Brush Script MT', cursive";
    ctx.fillText(value.trim().slice(0, 40), 24, canvas.height / 2 + 16);
    onChange(canvas.toDataURL("image/png"));
  }

  return (
    <div className={cn("grid gap-3", className)}>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={mode === "draw" ? "default" : "outline"}
          onClick={() => setMode("draw")}
        >
          Draw
        </Button>
        <Button
          type="button"
          size="sm"
          variant={mode === "type" ? "default" : "outline"}
          onClick={() => setMode("type")}
        >
          Type
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={clearCanvas}>
          Clear
        </Button>
      </div>
      {mode === "type" ? (
        <div className="grid gap-2">
          <Label htmlFor="typed-signature">Type your full legal name</Label>
          <Input
            id="typed-signature"
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
              renderTyped(event.target.value);
            }}
            autoComplete="name"
          />
        </div>
      ) : null}
      <canvas
        ref={canvasRef}
        width={640}
        height={180}
        className="bg-card touch-none w-full rounded-md border"
        aria-label="Signature pad"
        onPointerDown={(event) => {
          if (mode !== "draw") return;
          drawing.current = true;
          const ctx = canvasRef.current?.getContext("2d");
          const point = pointerPos(event);
          ctx?.beginPath();
          ctx?.moveTo(point.x, point.y);
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!drawing.current || mode !== "draw") return;
          const ctx = canvasRef.current?.getContext("2d");
          const point = pointerPos(event);
          ctx?.lineTo(point.x, point.y);
          ctx?.stroke();
        }}
        onPointerUp={() => {
          if (!drawing.current) return;
          drawing.current = false;
          emitCanvas();
        }}
      />
    </div>
  );
}
