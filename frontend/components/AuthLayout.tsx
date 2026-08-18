import type { ReactNode } from "react";

import { BrandMark } from "@/components/BrandMark";

/** Minimal branded chrome for Login and Onboarding — no public landing nav. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="flex h-16 items-center justify-center border-b">
        <div className="flex items-center gap-2">
          <span className="brand-surface grid size-9 place-items-center rounded-lg">
            <BrandMark className="size-7" />
          </span>
          <span className="text-base font-bold tracking-[-0.03em]">ONEST HUB</span>
        </div>
      </header>
      <main className="flex flex-1 flex-col">{children}</main>
    </div>
  );
}
