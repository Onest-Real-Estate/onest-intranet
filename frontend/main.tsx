import "./css/app.css";

import { createInertiaApp } from "@inertiajs/react";
import { LucideProvider } from "lucide-react";
import type { ComponentType } from "react";
import { createRoot } from "react-dom/client";

import type { PageProps } from "@/types";

const pages = import.meta.glob("./pages/**/*.tsx");

createInertiaApp<PageProps>({
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
        <App {...props} />
      </LucideProvider>,
    );
  },
  progress: {
    delay: 250,
    color: "#ddb52a",
    includeCSS: true,
    showSpinner: true,
  },
});
