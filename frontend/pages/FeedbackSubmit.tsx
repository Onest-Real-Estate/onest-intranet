import { Form, Head, Link, usePage } from "@inertiajs/react";
import {
  Bug,
  CircleHelp,
  FileWarning,
  Info,
  KeyRound,
  LifeBuoy,
  Lightbulb,
  Mail,
  Phone,
  ShieldCheck,
  UserRound,
  Wrench,
} from "lucide-react";
import { useMemo } from "react";

import {
  Callout,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  PageHeader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { IconWell, type IconWellTone } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useValidationToasts } from "@/hooks/use-validation-toasts";
import { routes } from "@/lib/routes";
import type { FeedbackSubmitPageProps } from "@/types";

/** A mark per category, keyed by the taxonomy's stable code. */
const CATEGORY_ICONS: Record<string, typeof Bug> = {
  bug: Bug,
  feature_idea: Lightbulb,
  content_correction: FileWarning,
  access_issue: KeyRound,
  general_help: LifeBuoy,
};

const CONTACT_ICONS: Record<string, typeof Bug> = {
  itSupport: Wrench,
  branchAdmin: UserRound,
  branchManager: ShieldCheck,
};

const CONTACT_TONES: Record<string, IconWellTone> = {
  itSupport: "info",
  branchAdmin: "muted",
  branchManager: "success",
};

/**
 * Everything the browser will report, gathered here and nowhere else.
 *
 * Deliberately five named fields rather than a scrape: the server drops
 * anything it did not ask for, so widening this object would achieve nothing
 * — but writing it out means a reader of this file can see the whole capture
 * without going to look.
 */
function collectMetadata(): Record<string, string> {
  if (typeof window === "undefined") return {};
  return {
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    locale: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    platform: navigator.platform ?? "",
    browser: navigator.userAgent.includes("Firefox")
      ? "Firefox"
      : navigator.userAgent.includes("Edg")
        ? "Edge"
        : navigator.userAgent.includes("Chrome")
          ? "Chrome"
          : navigator.userAgent.includes("Safari")
            ? "Safari"
            : "Other",
  };
}

/**
 * The support form.
 *
 * Uses Inertia's ``Form`` so named inputs (including the screenshot file)
 * submit without a full reload. Field errors stay inline; validation
 * refusals also toast via ``useValidationToasts``. Success flashes on
 * redirect to the ticket detail.
 *
 * The submission key is minted once per mount, so a double-clicked button or a
 * browser replaying the POST lands on the same ticket instead of two.
 */
export default function FeedbackSubmit() {
  const { categories, urgencies, disclosure, contacts, pageUrl, errors } =
    usePage<FeedbackSubmitPageProps>().props;
  useValidationToasts(errors, { title: "Could not send your report" });

  const submissionKey = useMemo(
    () =>
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    [],
  );
  const metadata = useMemo(() => JSON.stringify(collectMetadata()), []);

  return (
    <>
      <Head title="Get help" />
      <div className="grid gap-8">
        <PageHeader
          title="Get help"
          description="Tell us what happened. This goes to the people who can fix it."
          actions={
            <Button asChild variant="outline">
              <Link href={routes.feedback_mine()}>My reports</Link>
            </Button>
          }
        />

        <Form
          action={routes.feedback_create()}
          method="post"
          encType="multipart/form-data"
          className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
          disableWhileProcessing
        >
          {({ processing }) => (
            <>
              <input type="hidden" name="submissionKey" value={submissionKey} />
              <input type="hidden" name="browserMetadata" value={metadata} />
              <input type="hidden" name="pageUrl" value={pageUrl} />

              <div className="grid content-start gap-6">
                <SurfaceCard>
                  <PanelHeader divided title="Your report" />
                  <SurfaceCardContent className="grid gap-5">
                    {/* Native radios wearing cards. A five-way choice is the
                        first thing on the page and the thing people get wrong; as
                        a dropdown it is a list you have to open to read. Keyboard
                        and screen-reader behaviour is the browser's, not ours. */}
                    <fieldset className="grid gap-2">
                      <legend className="text-sm leading-none font-medium">
                        What kind of report is this?
                      </legend>
                      <div className="grid gap-2 @md:grid-cols-2">
                        {categories.map((option) => {
                          const Icon = CATEGORY_ICONS[option.value] ?? CircleHelp;
                          return (
                            <label
                              key={option.value}
                              className="border-border/70 hover:border-border-strong has-checked:border-chip-primary-edge has-checked:bg-chip-primary has-focus-visible:ring-ring group relative flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-[background-color,border-color] duration-(--motion-fast) has-focus-visible:ring-2"
                            >
                              <input
                                type="radio"
                                name="category"
                                value={option.value}
                                className="sr-only"
                              />
                              <IconWell
                                icon={Icon}
                                tone="muted"
                                className="size-8 group-has-checked:bg-brand-gold/20 group-has-checked:text-primary"
                                iconClassName="size-4"
                              />
                              <span className="min-w-0 text-sm leading-snug font-medium">
                                {option.label}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                      <FormFieldError
                        id="category-error"
                        message={errors.fields.category?.[0]}
                      />
                    </fieldset>

                    <FormField>
                      <FormLabel htmlFor="summary">One-line summary</FormLabel>
                      <Input
                        id="summary"
                        name="summary"
                        maxLength={160}
                        placeholder="Contracts page will not load"
                        aria-invalid={Boolean(errors.fields.summary?.[0])}
                        aria-errormessage={
                          errors.fields.summary?.[0] ? "summary-error" : undefined
                        }
                      />
                      <FormFieldError
                        id="summary-error"
                        message={errors.fields.summary?.[0]}
                      />
                    </FormField>

                    <FormField>
                      <FormLabel htmlFor="description">What happened?</FormLabel>
                      <Textarea
                        id="description"
                        name="description"
                        rows={6}
                        aria-describedby="description-help"
                        aria-invalid={Boolean(errors.fields.description?.[0])}
                        aria-errormessage={
                          errors.fields.description?.[0]
                            ? "description-error"
                            : undefined
                        }
                      />
                      <FormDescription id="description-help">
                        What you were doing, what you expected, and what happened
                        instead. Exact wording of any error helps.
                      </FormDescription>
                      <FormFieldError
                        id="description-error"
                        message={errors.fields.description?.[0]}
                      />
                    </FormField>

                    <fieldset className="grid gap-2">
                      <legend className="text-sm leading-none font-medium">
                        How urgent is this for you?
                      </legend>
                      <FormDescription id="urgency-help">
                        This is how it affects <em>you</em>. Support sets its own queue
                        order separately, so answering honestly costs nothing.
                      </FormDescription>
                      <div className="grid gap-2" aria-describedby="urgency-help">
                        {urgencies.map((option) => (
                          <label
                            key={option.value}
                            className="border-border/70 hover:border-border-strong has-checked:border-chip-primary-edge has-checked:bg-chip-primary has-focus-visible:ring-ring flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-[background-color,border-color] duration-(--motion-fast) has-focus-visible:ring-2"
                          >
                            <input
                              type="radio"
                              name="urgency"
                              value={option.value}
                              className="border-input text-primary size-4 shrink-0 accent-[var(--brand-gold)]"
                            />
                            <span className="min-w-0">{option.label}</span>
                          </label>
                        ))}
                      </div>
                      <FormFieldError
                        id="urgency-error"
                        message={errors.fields.urgency?.[0]}
                      />
                    </fieldset>

                    <FormField>
                      <FormLabel htmlFor="screenshot" optional>
                        Screenshot
                      </FormLabel>
                      <Input
                        id="screenshot"
                        name="screenshot"
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        aria-describedby="screenshot-help"
                        aria-invalid={Boolean(errors.fields.screenshot?.[0])}
                        aria-errormessage={
                          errors.fields.screenshot?.[0] ? "screenshot-error" : undefined
                        }
                      />
                      <FormDescription id="screenshot-help">
                        PNG, JPEG, or WebP. Only support staff can open it — but check
                        it does not show another person's details before you attach it.
                      </FormDescription>
                      <FormFieldError
                        id="screenshot-error"
                        message={errors.fields.screenshot?.[0]}
                      />
                    </FormField>

                    <div className="flex flex-wrap items-center gap-3">
                      <Button type="submit" disabled={processing}>
                        {processing ? "Sending…" : "Send report"}
                      </Button>
                      <span className="text-muted-foreground text-sm">
                        You will get a reference to follow it.
                      </span>
                    </div>
                  </SurfaceCardContent>
                </SurfaceCard>
              </div>

              <aside className="grid content-start gap-6">
                <SurfaceCard>
                  <PanelHeader
                    divided
                    title="What gets sent"
                    meta={
                      <span className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
                        <ShieldCheck className="size-3.5" aria-hidden />
                        Disclosed
                      </span>
                    }
                  />
                  <SurfaceCardContent className="grid gap-3">
                    {/* This list is generated on the server from the same constants
                        that do the capturing, so it cannot drift away from what is
                        actually stored. */}
                    <ul className="text-muted-foreground grid gap-2 text-sm leading-6">
                      {disclosure.map((line) => (
                        <li key={line} className="flex items-start gap-2">
                          <Info className="mt-1 size-3.5 shrink-0" aria-hidden />
                          <span>{line}</span>
                        </li>
                      ))}
                    </ul>
                    <Callout icon={LifeBuoy}>
                      Anything in the address of the page you were on that could be a
                      password or a token is removed before it is stored.
                    </Callout>
                  </SurfaceCardContent>
                </SurfaceCard>
              </aside>
            </>
          )}
        </Form>

        {contacts.length > 0 ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Or talk to somebody"
              description="The people who look after your office. A form is not always the fastest route."
            />
            <SurfaceCardContent className="grid gap-3 @2xl:grid-cols-3">
              {contacts.map((contact) => (
                <div
                  key={contact.key}
                  className="border-border/70 bg-card hover:border-border-strong grid content-start gap-2.5 rounded-lg border p-4 transition-colors duration-(--motion-fast)"
                >
                  <div className="flex items-start gap-3">
                    <IconWell
                      icon={CONTACT_ICONS[contact.key] ?? UserRound}
                      tone={CONTACT_TONES[contact.key] ?? "muted"}
                      className="size-9"
                    />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{contact.name}</p>
                      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                        {contact.role}
                      </p>
                    </div>
                  </div>
                  <p className="text-muted-foreground text-xs leading-5">
                    {contact.purpose}
                  </p>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Button
                      asChild
                      variant="outline"
                      size="sm"
                      className="h-7 px-2 text-xs"
                    >
                      <a href={`mailto:${contact.email}`} title={contact.email}>
                        <Mail className="size-3.5" aria-hidden />
                        Email
                      </a>
                    </Button>
                    {contact.phone ? (
                      <Button
                        asChild
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                      >
                        <a href={`tel:${contact.phone.replace(/[^+\d]/g, "")}`}>
                          <Phone className="size-3.5" aria-hidden />
                          <span className="tabular-nums">{contact.phone}</span>
                        </a>
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}
      </div>
    </>
  );
}

FeedbackSubmit.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Get help",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Get help", href: routes.feedback_submit() },
        ],
      },
      variant: "standard",
    },
  ] as const;
