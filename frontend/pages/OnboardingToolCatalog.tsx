import { Head, Link, router, usePage } from "@inertiajs/react";
import { ChevronDown, ChevronUp, GripVertical, Plus, X } from "lucide-react";
import { useState } from "react";

import {
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  NativeSelect,
  PageHeader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  CatalogTool,
  FilterOption,
  OnboardingToolCatalogPageProps,
} from "@/types";

/**
 * The guide editor.
 *
 * Steps are an ordered list, not a paragraph, so they are edited as one. A
 * textarea split on newlines looks simpler right up to the moment somebody
 * pastes a wrapped sentence and silently gains two steps.
 *
 * Each step posts as a repeated `step` field, which is what the server reads
 * with `getlist` — no client-side JSON assembly, so the form still works as a
 * plain POST.
 */
function StepsEditor({ initial, max }: { initial: string[]; max: number }) {
  const [steps, setSteps] = useState<string[]>(initial.length > 0 ? initial : [""]);

  function update(index: number, value: string) {
    setSteps((current) => current.map((step, i) => (i === index ? value : step)));
  }

  function move(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= steps.length) return;
    setSteps((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  return (
    <FormField>
      <FormLabel htmlFor="step-0" optional>
        Setup steps
      </FormLabel>
      <FormDescription id="steps-help">
        What the agent does, in order. Leave empty for a tool oNEST provisions — then
        the contact below is what they see instead.
      </FormDescription>
      <ol className="grid gap-2">
        {steps.map((step, index) => (
          // The index is the identity here: two steps may legitimately hold the
          // same text while being edited, and reordering must not remount them.
          // biome-ignore lint/suspicious/noArrayIndexKey: position is the identity
          <li key={index} className="flex items-center gap-2">
            <span className="text-muted-foreground w-4 shrink-0 text-xs tabular-nums">
              {index + 1}.
            </span>
            <Input
              id={`step-${index}`}
              name="step"
              value={step}
              maxLength={200}
              onChange={(event) => update(index, event.target.value)}
              placeholder="Go to narrpr.com and choose Create Account."
              aria-label={`Step ${index + 1}`}
            />
            <div className="flex shrink-0 items-center">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="size-8 p-0"
                disabled={index === 0}
                onClick={() => move(index, -1)}
                aria-label={`Move step ${index + 1} up`}
              >
                <ChevronUp className="size-4" aria-hidden />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="size-8 p-0"
                disabled={index === steps.length - 1}
                onClick={() => move(index, 1)}
                aria-label={`Move step ${index + 1} down`}
              >
                <ChevronDown className="size-4" aria-hidden />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="size-8 p-0"
                onClick={() =>
                  setSteps((current) =>
                    current.length === 1 ? [""] : current.filter((_, i) => i !== index),
                  )
                }
                aria-label={`Remove step ${index + 1}`}
              >
                <X className="size-4" aria-hidden />
              </Button>
            </div>
          </li>
        ))}
      </ol>
      {steps.length < max ? (
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSteps((current) => [...current, ""])}
          >
            <Plus aria-hidden />
            Add step
          </Button>
        </div>
      ) : (
        <p className="text-muted-foreground text-xs">
          {max} steps is the limit. Longer than that is a document, not a checklist —
          link to it above.
        </p>
      )}
    </FormField>
  );
}

/**
 * The editor for one tool.
 *
 * Posts natively, so a refused save comes back as an ordinary re-render with
 * the row still open and the draft echoed. Nothing is held in client state
 * that a failed save could lose.
 */
function ToolEditor({
  tool,
  offices,
  options,
  maxSteps,
  csrfToken,
  errors,
  draft,
}: {
  tool: CatalogTool | null;
  offices: FilterOption[];
  options: OnboardingToolCatalogPageProps["options"];
  maxSteps: number;
  csrfToken: string;
  errors: OnboardingToolCatalogPageProps["errors"];
  draft: OnboardingToolCatalogPageProps["draft"];
}) {
  const value = <K extends keyof CatalogTool>(key: K, draftKey: keyof typeof draft) =>
    (draft[draftKey] as CatalogTool[K]) ?? tool?.[key];

  const [companyWide, setCompanyWide] = useState(
    (draft.companyWide ?? tool?.companyWide ?? true) as boolean,
  );
  const selectedOffices = (draft.officeIds ?? tool?.officeIds ?? []) as number[];

  return (
    <form
      method="post"
      action={
        tool ? routes.onboarding_tool_save(tool.slug) : routes.onboarding_tool_create()
      }
      className="bg-muted/40 grid gap-5 px-5 py-5"
    >
      <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
      <FormErrorSummary errors={errors} />

      <div className="grid gap-4 @2xl:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="name" required>
            Name
          </FormLabel>
          <Input
            id="name"
            name="name"
            required
            maxLength={80}
            defaultValue={(value("name", "name") as string) ?? ""}
            aria-invalid={Boolean(errors.fields.name) || undefined}
          />
          <FormFieldError id="name-error" message={errors.fields.name?.[0]} />
        </FormField>
        <FormField>
          <FormLabel htmlFor="slug" required>
            Identifier
          </FormLabel>
          <Input
            id="slug"
            name="slug"
            required
            maxLength={60}
            defaultValue={(value("slug", "slug") as string) ?? ""}
            aria-describedby="slug-help"
            aria-invalid={Boolean(errors.fields.slug) || undefined}
          />
          <FormDescription id="slug-help">
            Stable and lower-case. It appears in audit records, so changing it later
            breaks the trail.
          </FormDescription>
          <FormFieldError id="slug-error" message={errors.fields.slug?.[0]} />
        </FormField>
      </div>

      <FormField>
        <FormLabel htmlFor="description" required>
          What it is for
        </FormLabel>
        <Input
          id="description"
          name="description"
          required
          maxLength={200}
          defaultValue={(value("description", "description") as string) ?? ""}
          placeholder="Transaction documents, signatures, and compliance files."
          aria-describedby="description-help"
          aria-invalid={Boolean(errors.fields.description) || undefined}
        />
        <FormDescription id="description-help">
          In the agent's terms, not the vendor's.
        </FormDescription>
        <FormFieldError
          id="description-error"
          message={errors.fields.description?.[0]}
        />
      </FormField>

      <div className="grid gap-4 @2xl:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="group" required>
            Shelf
          </FormLabel>
          <NativeSelect
            id="group"
            name="group"
            required
            defaultValue={(value("group", "group") as string) ?? ""}
          >
            <option value="">Choose a shelf</option>
            {options.groups.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <FormFieldError id="group-error" message={errors.fields.group?.[0]} />
        </FormField>
        <FormField>
          <FormLabel htmlFor="provisioning" required>
            Who creates the account
          </FormLabel>
          <NativeSelect
            id="provisioning"
            name="provisioning"
            required
            defaultValue={(value("provisioning", "provisioning") as string) ?? ""}
          >
            <option value="">Choose one</option>
            {options.provisioning.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <FormFieldError
            id="provisioning-error"
            message={errors.fields.provisioning?.[0]}
          />
        </FormField>
      </div>

      <StepsEditor
        initial={(draft.steps ?? tool?.steps ?? []) as string[]}
        max={maxSteps}
      />

      <FormField>
        <FormLabel htmlFor="contact_label" optional>
          Who to contact
        </FormLabel>
        <Input
          id="contact_label"
          name="contact_label"
          maxLength={120}
          defaultValue={(value("contact", "contact") as string) ?? ""}
          placeholder="IT support — we create the seat"
          aria-describedby="contact-help"
          aria-invalid={Boolean(errors.fields.contact_label) || undefined}
        />
        <FormDescription id="contact-help">
          Required when there are no steps. A tool an agent cannot act on is a dead row
          on their checklist.
        </FormDescription>
        <FormFieldError id="contact-error" message={errors.fields.contact_label?.[0]} />
      </FormField>

      <div className="grid gap-4 @2xl:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="open_url" optional>
            Open link
          </FormLabel>
          <Input
            id="open_url"
            name="open_url"
            type="url"
            defaultValue={(value("openUrl", "openUrl") as string) ?? ""}
            placeholder="https://…"
          />
          <FormFieldError id="open-url-error" message={errors.fields.open_url?.[0]} />
        </FormField>
        <FormField>
          <FormLabel htmlFor="help_url" optional>
            Vendor help link
          </FormLabel>
          <Input
            id="help_url"
            name="help_url"
            type="url"
            defaultValue={(value("helpUrl", "helpUrl") as string) ?? ""}
            placeholder="https://…"
          />
          <FormFieldError id="help-url-error" message={errors.fields.help_url?.[0]} />
        </FormField>
      </div>

      <FormField>
        <FormLabel htmlFor="company_wide">Applies to</FormLabel>
        <label htmlFor="company_wide" className="flex items-center gap-2 text-sm">
          <input
            id="company_wide"
            name="company_wide"
            type="checkbox"
            className="accent-primary size-4"
            checked={companyWide}
            onChange={(event) => setCompanyWide(event.target.checked)}
          />
          Every office
        </label>
        {companyWide ? null : (
          <div className="grid gap-1.5">
            <FormDescription id="offices-help">
              Naming a region or state covers every office beneath it — an MLS attaches
              once, not once per branch.
            </FormDescription>
            <div className="border-border/70 grid max-h-56 gap-1 overflow-y-auto rounded-md border p-3">
              {offices.map((office) => (
                <label
                  key={office.value}
                  className="flex items-center gap-2 text-sm"
                  htmlFor={`office-${office.value}`}
                >
                  <input
                    id={`office-${office.value}`}
                    type="checkbox"
                    name="offices"
                    value={office.value}
                    defaultChecked={selectedOffices.includes(Number(office.value))}
                    className="accent-primary size-4"
                  />
                  {office.label}
                </label>
              ))}
            </div>
            <FormFieldError id="offices-error" message={errors.fields.offices?.[0]} />
          </div>
        )}
      </FormField>

      {/* Two distinct settings, so they get two rows. Side by side they read as
          one control with a stray second box, and each needs a sentence saying
          what it changes. */}
      <div className="border-border/70 grid gap-3 border-t pt-4">
        <label htmlFor="is_required" className="flex items-start gap-2.5 text-sm">
          <input
            id="is_required"
            name="is_required"
            type="checkbox"
            className="accent-primary mt-0.5 size-4 shrink-0"
            defaultChecked={(draft.required ?? tool?.required ?? true) as boolean}
          />
          <span className="grid gap-0.5">
            <span className="font-medium">Expected of every agent</span>
            <span className="text-muted-foreground text-xs">
              Counts toward their readiness figure. Turn off for a tool that is
              available but optional.
            </span>
          </span>
        </label>
        <label htmlFor="is_active" className="flex items-start gap-2.5 text-sm">
          <input
            id="is_active"
            name="is_active"
            type="checkbox"
            className="accent-primary mt-0.5 size-4 shrink-0"
            defaultChecked={(draft.active ?? tool?.active ?? true) as boolean}
          />
          <span className="grid gap-0.5">
            <span className="font-medium">Active</span>
            <span className="text-muted-foreground text-xs">
              Off removes it from every checklist without deleting anybody's recorded
              progress.
            </span>
          </span>
        </label>
        <input
          type="hidden"
          name="sort_order"
          value={String(draft.sortOrder ?? tool?.sortOrder ?? 0)}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit">{tool ? "Save changes" : "Add tool"}</Button>
        <Button asChild variant="ghost">
          <Link href={routes.onboarding_tool_catalog()}>Cancel</Link>
        </Button>
      </div>
    </form>
  );
}

function CatalogRow({
  tool,
  index,
  count,
  editing,
  onMove,
  children,
}: {
  tool: CatalogTool;
  index: number;
  count: number;
  editing: boolean;
  /** The whole group's order is the unit of change, so the move is computed
   *  where the sibling list is known rather than guessed from one row. */
  onMove: (index: number, delta: -1 | 1) => void;
  children: React.ReactNode;
}) {
  return (
    <li className="border-border/70 border-b last:border-b-0">
      <div
        className={cn(
          "flex flex-wrap items-center gap-3 px-5 py-3.5",
          !tool.active && "opacity-60",
        )}
      >
        <GripVertical className="text-muted-foreground size-4 shrink-0" aria-hidden />
        <div className="grid min-w-0 flex-1 gap-0.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-medium">{tool.name}</span>
            {tool.active ? null : (
              <span className="text-muted-foreground text-micro font-medium tracking-[0.02em] uppercase">
                Inactive
              </span>
            )}
            {tool.required ? null : (
              <span className="text-muted-foreground text-micro font-medium tracking-[0.02em] uppercase">
                Optional
              </span>
            )}
          </div>
          <span className="text-muted-foreground truncate text-xs">
            {tool.provisioningLabel} · {tool.appliesTo} ·{" "}
            {tool.steps.length > 0
              ? `${tool.steps.length} step${tool.steps.length === 1 ? "" : "s"}`
              : "no steps"}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="size-8 p-0"
            disabled={index === 0}
            onClick={() => onMove(index, -1)}
            aria-label={`Move ${tool.name} up`}
          >
            <ChevronUp className="size-4" aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="size-8 p-0"
            disabled={index === count - 1}
            onClick={() => onMove(index, 1)}
            aria-label={`Move ${tool.name} down`}
          >
            <ChevronDown className="size-4" aria-hidden />
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link
              href={
                editing
                  ? routes.onboarding_tool_catalog()
                  : `${routes.onboarding_tool_catalog()}?edit=${tool.slug}`
              }
            >
              {editing ? "Close" : "Edit"}
            </Link>
          </Button>
        </div>
      </div>
      {editing ? children : null}
    </li>
  );
}

/**
 * The catalog every agent's checklist is built from.
 *
 * Editing happens in place: a row opens into its own form rather than sending
 * an administrator to a separate page and back. At two dozen rows across three
 * shelves, keeping the list on screen is what makes "does this read right next
 * to its neighbours" answerable while editing.
 */
export default function OnboardingToolCatalog() {
  const { groups, offices, options, maxSteps, editing, draft, errors, csrfToken } =
    usePage<OnboardingToolCatalogPageProps>().props;

  const creating = editing === "new";

  return (
    <PermissionRequired permission={{ all: ["web.manage_onboarding_tools"] }}>
      <div className="grid gap-8">
        <Head title="Tool catalog" />
        <PageHeader
          title="Tool catalog"
          description="What every agent is set up with, where each one applies, and the guide they follow."
          actions={
            creating ? null : (
              <Button asChild>
                <Link href={`${routes.onboarding_tool_catalog()}?edit=new`}>
                  <Plus aria-hidden />
                  Add tool
                </Link>
              </Button>
            )
          }
        />

        {creating ? (
          <SurfaceCard>
            <PanelHeader divided title="New tool" />
            <SurfaceCardContent className="px-0">
              <ToolEditor
                tool={null}
                offices={offices}
                options={options}
                maxSteps={maxSteps}
                csrfToken={csrfToken}
                errors={errors}
                draft={draft}
              />
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {groups.map((group) => {
          function moveWithin(index: number, delta: -1 | 1) {
            const target = index + delta;
            if (target < 0 || target >= group.tools.length) return;
            const order = group.tools.map((row) => row.slug);
            [order[index], order[target]] = [order[target], order[index]];
            // The complete intended sequence, so the server never has to
            // reconstruct a move from a delta it did not witness.
            router.post(
              routes.onboarding_tool_reorder(),
              { group: group.code, order },
              { preserveScroll: true },
            );
          }

          return (
            <SurfaceCard key={group.code}>
              <PanelHeader
                divided
                title={group.label}
                headingLevel="h2"
                meta={
                  <span className="text-muted-foreground text-xs tabular-nums">
                    {group.tools.length} {group.tools.length === 1 ? "tool" : "tools"}
                  </span>
                }
              />
              <SurfaceCardContent className="px-0">
                <ul>
                  {group.tools.map((tool, index) => (
                    <CatalogRow
                      key={tool.slug}
                      tool={tool}
                      index={index}
                      count={group.tools.length}
                      editing={editing === tool.slug}
                      onMove={moveWithin}
                    >
                      <ToolEditor
                        tool={tool}
                        offices={offices}
                        options={options}
                        maxSteps={maxSteps}
                        csrfToken={csrfToken}
                        errors={errors}
                        draft={draft}
                      />
                    </CatalogRow>
                  ))}
                </ul>
              </SurfaceCardContent>
            </SurfaceCard>
          );
        })}
      </div>
    </PermissionRequired>
  );
}

OnboardingToolCatalog.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Tool catalog",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Tool catalog" },
        ],
      },
    },
  ] as const;
