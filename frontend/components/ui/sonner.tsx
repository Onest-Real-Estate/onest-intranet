import { useEffect, useState } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

import type { ResolvedTheme } from "@/lib/theme";

/**
 * Follow the document ``dark`` class — the same switch the pre-paint script and
 * ``useTheme`` write — so the toaster cannot drift from the page when Sonner
 * keeps its own theme prop.
 */
function useDocumentTheme(): ResolvedTheme {
  const [theme, setTheme] = useState<ResolvedTheme>(() =>
    typeof document !== "undefined" &&
    document.documentElement.classList.contains("dark")
      ? "dark"
      : "light",
  );

  useEffect(() => {
    const root = document.documentElement;
    const sync = () => {
      setTheme(root.classList.contains("dark") ? "dark" : "light");
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return theme;
}

/**
 * App-wide toast host. Mount once near the root so any page can call
 * ``toast.error`` / ``toast.success`` without a local portal.
 *
 * Colours come from hub tokens (see ``[data-sonner-toaster]`` in ``app.css``),
 * not Sonner's built-in light/dark palette, so rich-colour levels match Callout
 * / StatusBadge chips in both themes.
 */
export function Toaster({ ...props }: ToasterProps) {
  const theme = useDocumentTheme();

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      position="top-right"
      closeButton
      richColors
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:shadow-popover group-[.toaster]:rounded-(--radius-card)",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton: "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
          closeButton:
            "group-[.toast]:border-border group-[.toast]:bg-background group-[.toast]:text-foreground",
        },
      }}
      {...props}
    />
  );
}
