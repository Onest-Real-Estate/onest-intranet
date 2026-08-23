import { Link } from "@inertiajs/react";
import {
  AppWindow,
  Building2,
  CalendarClock,
  CalendarRange,
  ExternalLink,
  FilePlus,
  FileSignature,
  FileText,
  FolderPlus,
  Globe2,
  GraduationCap,
  Home,
  LifeBuoy,
  type LucideIcon,
  Megaphone,
  Package,
  PackagePlus,
  Plus,
  Search,
  Sparkles,
  UserPlus,
  UserRoundPlus,
  UserRoundSearch,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  EmptyState,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { QuickCreate, QuickCreateAction } from "@/types";

/**
 * Icon names the registry may use. A name with no entry falls back to a
 * neutral mark rather than crashing the header — the server owns the catalog,
 * so this map is allowed to lag a new entry by one deploy.
 */
const ICONS: Record<string, LucideIcon> = {
  "app-window": AppWindow,
  "calendar-clock": CalendarClock,
  "calendar-range": CalendarRange,
  "file-plus": FilePlus,
  "file-signature": FileSignature,
  "file-text": FileText,
  "folder-plus": FolderPlus,
  "graduation-cap": GraduationCap,
  home: Home,
  "life-buoy": LifeBuoy,
  megaphone: Megaphone,
  package: Package,
  "package-plus": PackagePlus,
  "user-plus": UserPlus,
  "user-round-plus": UserRoundPlus,
  "user-round-search": UserRoundSearch,
};

function matches(action: QuickCreateAction, term: string): boolean {
  const needle = term.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return (
    action.label.toLowerCase().includes(needle) ||
    action.description.toLowerCase().includes(needle) ||
    action.group.toLowerCase().includes(needle)
  );
}

/**
 * The global Quick Create menu.
 *
 * The action list arrives already filtered by the server — permission, scope,
 * and feature availability are all decided before serialization, so this
 * component never asks whether somebody *may* do something. It renders what it
 * was given, and every destination re-enforces its own authorization on
 * arrival, so a crafted navigation is refused whether or not the menu offered
 * it.
 *
 * One registry drives both entry points: the header button on desktop and the
 * same button in the mobile header. There is no second list to fall out of step.
 */
export function QuickCreateMenu({ quickCreate }: { quickCreate?: QuickCreate }) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  // The trigger is an ordinary button rather than a `DialogTrigger`, so Radix
  // has no element to hand focus back to on close. Returning it here keeps a
  // keyboard reader where they were instead of dropping them on <body>.
  const triggerRef = useRef<HTMLButtonElement>(null);

  const actions = quickCreate?.actions ?? [];
  const visible = useMemo(
    () => actions.filter((action) => matches(action, term)),
    [actions, term],
  );
  const groups = useMemo(() => {
    const ordered: { group: string; items: QuickCreateAction[] }[] = [];
    for (const action of visible) {
      const bucket = ordered.find((entry) => entry.group === action.group);
      if (bucket) {
        bucket.items.push(action);
      } else {
        ordered.push({ group: action.group, items: [action] });
      }
    }
    return ordered;
  }, [visible]);

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            ref={triggerRef}
            type="button"
            variant="ghost"
            size="icon"
            className="size-9"
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-label="Create new"
            onClick={() => {
              setTerm("");
              setOpen(true);
            }}
          >
            <Plus className="size-5" strokeWidth={1.5} aria-hidden />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Create new</TooltipContent>
      </Tooltip>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          // Focus lands on the search box when there is one, and on the dialog
          // otherwise; Radix restores it to the trigger on close.
          onOpenAutoFocus={(event) => {
            if (quickCreate?.searchable) {
              event.preventDefault();
              searchRef.current?.focus();
            }
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            triggerRef.current?.focus();
          }}
          className="max-w-lg"
        >
          <DialogHeader>
            <DialogTitle>Create new</DialogTitle>
            <DialogDescription>
              {quickCreate?.scope ? (
                <span className="flex items-center gap-1.5">
                  {quickCreate.scope.level === "brokerage" ? (
                    <Globe2 className="size-3.5 shrink-0" aria-hidden />
                  ) : (
                    <Building2 className="size-3.5 shrink-0" aria-hidden />
                  )}
                  {/* Which offices these actions apply to, said plainly: a
                      regional manager and a branch admin see the same labels
                      and should not have to guess which hat they are wearing. */}
                  Acting for {quickCreate.scope.label}
                </span>
              ) : (
                "Start something new."
              )}
            </DialogDescription>
          </DialogHeader>

          {quickCreate?.searchable ? (
            <div className="relative">
              <Search
                className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                aria-hidden
              />
              <Input
                ref={searchRef}
                value={term}
                onChange={(event) => setTerm(event.target.value)}
                placeholder="Search actions"
                aria-label="Search actions"
                className="pl-9"
              />
            </div>
          ) : null}

          {actions.length === 0 ? (
            <EmptyState
              icon={Sparkles}
              title="Nothing to create yet"
              description="Actions appear here as modules switch on for your role and offices."
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No actions match"
              description={`Nothing matches “${term.trim()}”. Try a shorter word.`}
            />
          ) : (
            <div className="grid max-h-[60vh] gap-4 overflow-y-auto">
              {groups.map((group) => (
                <section key={group.group} className="grid gap-1.5">
                  <h3 className="text-muted-foreground px-1 text-xs font-semibold tracking-[0.06em] uppercase">
                    {group.group}
                  </h3>
                  <ul className="grid gap-1">
                    {group.items.map((action) => {
                      const Icon = ICONS[action.icon] ?? Sparkles;
                      return (
                        <li key={action.key}>
                          <Link
                            href={action.href}
                            onClick={() => setOpen(false)}
                            className="hover:bg-muted focus-visible:ring-ring flex items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
                          >
                            <span className="bg-muted text-foreground mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg">
                              <Icon className="size-4" aria-hidden />
                            </span>
                            <span className="grid min-w-0 gap-0.5">
                              <span className="flex items-center gap-1.5 text-sm font-semibold">
                                {action.label}
                                {action.external ? (
                                  <>
                                    <ExternalLink
                                      className="size-3.5 shrink-0"
                                      aria-hidden
                                    />
                                    <span className="sr-only">(leaves the hub)</span>
                                  </>
                                ) : null}
                              </span>
                              <span className="text-muted-foreground text-xs leading-5">
                                {action.description}
                              </span>
                            </span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
