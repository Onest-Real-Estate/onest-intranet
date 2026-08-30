import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useTheme } from "@/hooks/use-theme";
import { resolveTheme } from "@/lib/theme";

/**
 * App-wide toast host. Mount once near the root so any page can call
 * ``toast.error`` / ``toast.success`` without a local portal.
 */
export function Toaster({ ...props }: ToasterProps) {
  const { preference } = useTheme();
  const theme = resolveTheme(preference);

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
            "group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton: "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props}
    />
  );
}
