import "./css/app.css";

import { createInertiaApp } from "@inertiajs/react";
import { LucideProvider } from "lucide-react";
import type { ComponentType } from "react";
import { createRoot } from "react-dom/client";

import { AppErrorBoundary, RecoverableError } from "@/components/AppErrorBoundary";
import type { PageProps } from "@/types";

const pages = import.meta.glob("./pages/**/*.tsx");

const application = createInertiaApp<PageProps>({
  title: (title) => (title ? `${title} · Onest` : "Onest"),
  resolve: (name) => {
    const page = pages[`./pages/${name}.tsx`];
    if (!page) {
      throw new Error(`Inertia page not found: ${name}`);
    }
    return page().then((module) => (module as { default: ComponentType }).default);
  },
  setup({ el, App, props }) {
    createRoot(el).render(
      <LucideProvider strokeWidth={1.5} size={20}>
        <AppErrorBoundary>
          <App {...props} />
        </AppErrorBoundary>
      </LucideProvider>,
    );
  },
  progress: {
    delay: 250,
    color: "var(--primary)",
    includeCSS: true,
    showSpinner: false,
  },
});

// Initial page chunks resolve before React mounts, so they sit outside the
// boundary above. Preserve a usable recovery screen even in that narrow case.
void application.catch(() => {
  const element = document.getElementById("app");
  if (element) {
    createRoot(element).render(
      <RecoverableError onRetry={() => window.location.reload()} />,
    );
  }
});
