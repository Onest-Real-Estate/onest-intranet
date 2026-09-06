import { Head, Link, usePage } from "@inertiajs/react";
import { Send, Ticket } from "lucide-react";
import { useId, useMemo } from "react";

import {
  EmptyState,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  NativeSelect,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type { ITSupportPageProps, SupportTicketRow } from "@/types";

function formatDay(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
}

/**
 * One of the reader's own tickets, as a ruled row.
 *
 * A grid of bordered cards would float one box per ticket; a ruled list puts
 * every reference on one left edge and every status on one right edge, so the
 * column scans as a record rather than as a set of objects to compare.
 */
function TicketRow({ ticket }: { ticket: SupportTicketRow }) {
  return (
    <li>
      <Link
        href={routes.it_support_ticket(ticket.id)}
        className="hover:bg-accent/40 focus-visible:ring-ring -mx-5 flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3.5 transition-colors focus-visible:ring-2 focus-visible:outline-none"
      >
        <span className="text-muted-foreground w-24 shrink-0 text-xs font-medium tabular-nums">
          {ticket.reference}
        </span>
        <span className="grid min-w-0 flex-1 gap-0.5">
          <span className="truncate text-sm font-medium">{ticket.subject}</span>
          <span className="text-muted-foreground truncate text-xs">
            {ticket.category.label} · opened {formatDay(ticket.createdAt)}
            {ticket.assignee ? ` · with ${ticket.assignee.name}` : ""}
          </span>
        </span>
        <StatusBadge status={ticket.status} />
      </Link>
    </li>
  );
}

/**
 * Raise an IT request, and read the ones you already raised.
 *
 * The form posts natively rather than through the Inertia router: one code
 * path whether or not somebody attaches a file, and a refused save comes back
 * as an ordinary re-render with the draft echoed so nothing typed is lost.
 *
 * `submissionKey` is generated once per render and travels with the post. It
 * is what makes a double-clicked button, a retried request, and a browser
 * replaying the POST all land on the same ticket.
 */
export default function ITSupport() {
  const { tickets, openCount, options, draft, errors, csrfToken } =
    usePage<ITSupportPageProps>().props;
  const formId = useId();
  const submissionKey = useMemo(
    () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
    [],
  );

  return (
    <div className="grid gap-8">
      <Head title="IT support" />
      <PageHeader
        title="IT support"
        description="Tell the IT team what is not working, and follow what they do about it."
      />

      <div className="grid items-start gap-6 @4xl:grid-cols-[minmax(0,1fr)_22rem]">
        <SurfaceCard>
          <PanelHeader
            divided
            title="Raise a request"
            description="The more specific the better — what you tried, and what happened."
          />
          <SurfaceCardContent>
            <form
              id={formId}
              method="post"
              action={routes.it_support_create()}
              encType="multipart/form-data"
              className="grid gap-4"
            >
              <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
              <input type="hidden" name="submissionKey" value={submissionKey} />

              <FormErrorSummary errors={errors} />

              <FormField>
                <FormLabel htmlFor="subject" required>
                  What is the problem?
                </FormLabel>
                <Input
                  id="subject"
                  name="subject"
                  required
                  maxLength={160}
                  defaultValue={draft.subject ?? ""}
                  placeholder="Printer on the second floor will not accept my login"
                  aria-invalid={Boolean(errors.fields.subject) || undefined}
                />
                <FormFieldError
                  id="subject-error"
                  message={errors.fields.subject?.[0]}
                />
              </FormField>

              <FormField>
                <FormLabel htmlFor="category" required>
                  Category
                </FormLabel>
                <NativeSelect
                  id="category"
                  name="category"
                  required
                  defaultValue={draft.category ?? ""}
                  aria-invalid={Boolean(errors.fields.category) || undefined}
                >
                  <option value="">Choose the closest match</option>
                  {options.categories.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </NativeSelect>
                <FormFieldError
                  id="category-error"
                  message={errors.fields.category?.[0]}
                />
              </FormField>

              <FormField>
                <FormLabel htmlFor="description" required>
                  What happens?
                </FormLabel>
                <Textarea
                  id="description"
                  name="description"
                  rows={5}
                  required
                  defaultValue={draft.description ?? ""}
                  placeholder="What you were doing, what you expected, and what happened instead."
                  aria-invalid={Boolean(errors.fields.description) || undefined}
                />
                <FormFieldError
                  id="description-error"
                  message={errors.fields.description?.[0]}
                />
              </FormField>

              <div className="grid gap-4 @lg:grid-cols-2">
                <FormField>
                  <FormLabel htmlFor="location" optional>
                    Where are you?
                  </FormLabel>
                  <Input
                    id="location"
                    name="location"
                    maxLength={120}
                    defaultValue={draft.location ?? ""}
                    placeholder="Branford front desk"
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="preferredContact">
                    How should we reach you?
                  </FormLabel>
                  <NativeSelect
                    id="preferredContact"
                    name="preferredContact"
                    defaultValue={draft.preferredContact || "hub"}
                  >
                    {options.contactMethods.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </NativeSelect>
                </FormField>
              </div>

              <FormField>
                <FormLabel htmlFor="deviceInfo" optional>
                  Device or browser
                </FormLabel>
                <Input
                  id="deviceInfo"
                  name="deviceInfo"
                  maxLength={300}
                  defaultValue={draft.deviceInfo ?? ""}
                  placeholder="Work laptop, Chrome"
                  aria-describedby="device-help"
                />
                <FormDescription id="device-help">
                  Only what you want to say. Nothing is collected from your machine
                  without you typing it here.
                </FormDescription>
              </FormField>

              <FormField>
                <FormLabel htmlFor="file" optional>
                  Attach a screenshot or file
                </FormLabel>
                <input
                  id="file"
                  name="file"
                  type="file"
                  className="border-input file:text-foreground focus-visible:border-ring focus-visible:ring-ring/50 flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs file:mr-3 file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:ring-[3px] focus-visible:outline-none"
                  aria-describedby="file-help"
                />
                <FormDescription id="file-help">
                  Up to 10 MB. Images, PDF, Office documents, logs, CSV, or text.
                </FormDescription>
                <FormFieldError id="file-error" message={errors.fields.file?.[0]} />
              </FormField>

              <div>
                <Button type="submit">
                  <Send aria-hidden />
                  Send to IT
                </Button>
              </div>
            </form>
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <PanelHeader
            divided
            title="Your requests"
            meta={
              openCount > 0 ? (
                <span className="text-muted-foreground text-xs">{openCount} open</span>
              ) : null
            }
          />
          <SurfaceCardContent>
            {tickets.length > 0 ? (
              <ul className="divide-border/70 divide-y">
                {tickets.map((ticket) => (
                  <TicketRow key={ticket.id} ticket={ticket} />
                ))}
              </ul>
            ) : (
              <EmptyState
                compact
                tone="muted"
                icon={Ticket}
                title="Nothing raised yet"
                description="Requests you send appear here so you can follow what IT is doing."
              />
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </div>
  );
}

ITSupport.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "IT support",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "IT support" },
        ],
      },
    },
  ] as const;
