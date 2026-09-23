import { Head, router, usePage } from "@inertiajs/react";
import { ArrowRight, CheckCircle2, Lock } from "lucide-react";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import { Callout, FormActionBar, FormErrorSummary } from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { ProfileAdministrativePanel } from "@/components/profile/ProfileAdministrativePanel";
import {
  ProfileAddressSection,
  ProfileBiographySection,
  ProfileContactSection,
  ProfileCredentialsSection,
  ProfileLinksSection,
  SECTION_ANCHORS,
} from "@/components/profile/ProfileFormSections";
import { ProfileIdentityPanel } from "@/components/profile/ProfileIdentityPanel";
import { ProfilePhotoPanel } from "@/components/profile/ProfilePhotoPanel";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { hasValidationErrors } from "@/lib/validation";
import type { ProfilePageProps } from "@/types";

/** Django field name → the wording used in the error summary. */
const ERROR_LABELS: Record<string, string> = {
  first_name: "First name",
  last_name: "Last name",
  preferred_name: "Preferred name",
  phone_number: "Phone number",
  preferred_contact_method: "Preferred contact method",
  street_address: "Street address",
  city: "City",
  state: "State",
  zip_code: "ZIP code",
  office: "Office location",
  mls_number: "MLS number",
  nrds_number: "NRDS number",
  license_number: "License number",
  license_state: "License state",
  license_expires_on: "License expiration",
  bio: "Professional bio",
  languages: "Languages",
  specialties: "Specialties",
  website_url: "Website",
  linkedin_url: "LinkedIn",
  facebook_url: "Facebook",
  instagram_url: "Instagram",
  x_url: "X",
};

type TabKey = "personal" | "professional" | "account";

const TABS: { key: TabKey; label: string; sections: string[] }[] = [
  { key: "personal", label: "Personal", sections: ["contact", "address", "photo"] },
  {
    key: "professional",
    label: "Professional",
    sections: ["credentials", "biography", "links"],
  },
  { key: "account", label: "Account", sections: [] },
];

/** Which tab owns each posted field, so a refused save opens where the error is. */
const FIELD_TAB: Record<string, TabKey> = {
  first_name: "personal",
  last_name: "personal",
  preferred_name: "personal",
  phone_number: "personal",
  preferred_contact_method: "personal",
  street_address: "personal",
  city: "personal",
  state: "personal",
  zip_code: "personal",
};

function tabOfField(field: string): TabKey {
  return FIELD_TAB[field] ?? "professional";
}

function tabOfSection(section: string): TabKey {
  return TABS.find((tab) => tab.sections.includes(section))?.key ?? "personal";
}

function tabFromHash(): TabKey {
  if (typeof window === "undefined") return "personal";
  const hash = window.location.hash.replace("#", "");
  return TABS.some((tab) => tab.key === hash) ? (hash as TabKey) : "personal";
}

/**
 * The self-service profile, as a settings page.
 *
 * Three tabs split a long form into what a person looks for: how to reach
 * them, their professional record, and the account facts they cannot change.
 * The tabs are presentation only — every editable field stays mounted inside
 * one form, so Save posts the whole set as one Inertia visit and a validation
 * failure anywhere leaves everything typed intact. The photo saves on its own
 * endpoint and sits above the form for that reason.
 */
export default function Profile() {
  const {
    csrfToken,
    initial,
    validation,
    offices,
    states,
    languageOptions,
    specialtyOptions,
    contactMethods,
    socialPlatforms,
    identity,
    editable,
    completeness,
    limits,
    shell,
  } = usePage<ProfilePageProps>().props;

  const [tab, setTab] = useState<TabKey>(tabFromHash);
  const [dirty, setDirty] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<Record<TabKey, HTMLButtonElement | null>>({
    personal: null,
    professional: null,
    account: null,
  });
  const hasErrors = hasValidationErrors(validation);

  const errorsByTab = Object.keys(validation.fields).reduce<Record<TabKey, number>>(
    (counts, field) => {
      counts[tabOfField(field)] += 1;
      return counts;
    },
    { personal: 0, professional: 0, account: 0 },
  );

  function selectTab(next: TabKey, focus = false) {
    setTab(next);
    // The hash, not a visit: switching tabs must not reload or lose edits,
    // but a link or a refresh should still land on the same tab.
    window.history.replaceState(window.history.state, "", `#${next}`);
    if (focus) tabRefs.current[next]?.focus();
  }

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const index = TABS.findIndex((item) => item.key === tab);
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step !== 0) {
      event.preventDefault();
      selectTab(TABS[(index + step + TABS.length) % TABS.length].key, true);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      selectTab(TABS[event.key === "Home" ? 0 : TABS.length - 1].key, true);
    }
  }

  // Guard the browser's own navigation away from unsaved edits.
  useEffect(() => {
    if (!dirty) {
      return;
    }
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  // A 422 re-renders with errors: open the tab holding the first one and move
  // focus to the summary, which links to each field.
  useEffect(() => {
    if (!hasErrors) return;
    const first = Object.keys(validation.fields)[0];
    if (first) setTab(tabOfField(first));
    summaryRef.current?.focus();
  }, [hasErrors, validation.fields]);

  const sectionProps = { initial, validation, onDirty: () => setDirty(true) };
  const missing = completeness.missing;
  const firstMissing = missing[0];

  function finishProfile() {
    if (!firstMissing) return;
    const next = tabOfSection(firstMissing.section);
    selectTab(next);
    const anchor = SECTION_ANCHORS[firstMissing.section];
    window.requestAnimationFrame(() =>
      document.getElementById(anchor)?.scrollIntoView({ block: "start" }),
    );
  }

  return (
    <div className="grid gap-6">
      <Head title="Your profile" />
      <header className="grid gap-1">
        <h1 className="text-2xl leading-8 font-bold tracking-[-0.02em]">
          Your profile
        </h1>
        <p className="text-muted-foreground max-w-measure text-sm leading-6">
          Manage how colleagues and clients see and reach you.{" "}
          <span className="inline-flex items-center gap-1 whitespace-nowrap">
            <Lock className="size-3.5" aria-hidden />
            Only you and your brokerage can change it.
          </span>
        </p>
      </header>

      <ProfilePhotoPanel
        headshotUrl={initial.headshotUrl}
        displayName={identity.preferredDisplayName || identity.displayName}
        csrfToken={csrfToken}
        limits={limits}
        details={
          <>
            <span className="truncate">{identity.email}</span>
            {identity.roles[0] ? (
              <>
                <span aria-hidden>·</span>
                <span>{identity.roles[0]}</span>
              </>
            ) : null}
            {identity.office ? (
              <>
                <span aria-hidden>·</span>
                <span>{identity.office.name}</span>
              </>
            ) : null}
          </>
        }
        aside={
          completeness.percent === 100 ? (
            <span className="bg-chip-success border-chip-success-edge text-success inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold">
              <CheckCircle2 className="size-3.5" aria-hidden />
              Profile complete
            </span>
          ) : (
            <div className="grid min-w-44 gap-1.5">
              <p className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-muted-foreground">Profile complete</span>
                <span className="font-semibold tabular-nums">
                  {completeness.percent}%
                </span>
              </p>
              <div
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={completeness.percent}
                aria-label={`Profile ${completeness.percent} percent complete`}
                className="bg-muted h-1.5 overflow-hidden rounded-full"
              >
                <div
                  className={cn(
                    "h-full rounded-full transition-[width] duration-(--motion-slow)",
                    completeness.percent === 100 ? "bg-success" : "bg-primary",
                  )}
                  style={{ width: `${completeness.percent}%` }}
                />
              </div>
              <p className="text-muted-foreground text-xs tabular-nums">
                {completeness.completed} of {completeness.total} details
              </p>
            </div>
          )
        }
      />

      {firstMissing ? (
        <Callout
          tone={missing.some((item) => item.required) ? "warning" : "info"}
          title={
            missing.some((item) => item.required)
              ? "Some required details are missing"
              : "A few details would round out your profile"
          }
          action={
            <Button type="button" variant="outline" size="sm" onClick={finishProfile}>
              Add {firstMissing.label.toLowerCase()}
              <ArrowRight aria-hidden />
            </Button>
          }
        >
          <p className="text-muted-foreground">
            Still to add:{" "}
            {missing
              .slice(0, 3)
              .map((item) => item.label)
              .join(", ")}
            {missing.length > 3 ? `, and ${missing.length - 3} more` : ""}.
          </p>
        </Callout>
      ) : null}

      <div
        role="tablist"
        aria-label="Profile sections"
        className="bg-muted inline-flex w-fit max-w-full gap-0.5 overflow-x-auto rounded-md p-0.5"
      >
        {TABS.map((item) => {
          const selected = tab === item.key;
          const errorCount = errorsByTab[item.key];
          return (
            <button
              key={item.key}
              ref={(node) => {
                tabRefs.current[item.key] = node;
              }}
              type="button"
              role="tab"
              id={`tab-${item.key}`}
              aria-selected={selected}
              aria-controls={`panel-${item.key}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => selectTab(item.key)}
              onKeyDown={onTabKeyDown}
              className={cn(
                "focus-visible:ring-ring/50 inline-flex h-9 items-center gap-2 rounded-sm px-4 text-sm font-medium whitespace-nowrap outline-none transition-colors duration-(--motion-fast) focus-visible:ring-[3px]",
                selected
                  ? "bg-card text-foreground shadow-card"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item.label}
              {errorCount > 0 ? (
                <span className="bg-chip-destructive border-chip-destructive-edge text-destructive rounded-sm border px-1 text-xs tabular-nums">
                  <span className="sr-only">, </span>
                  {errorCount}
                  <span className="sr-only">
                    {" "}
                    {errorCount === 1 ? "error" : "errors"}
                  </span>
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <form
        id="profile-form"
        method="post"
        action={routes.profile_submit()}
        className="grid gap-6"
        // Delegated: every uncontrolled text input in the sections below
        // reports through here, so no field has to thread a callback.
        onInput={() => setDirty(true)}
        onSubmit={(event) => {
          event.preventDefault();
          if (submitting) {
            return;
          }
          setSubmitting(true);
          const form = event.currentTarget;
          // FormData so Django request.POST receives the fields (JSON bodies
          // do not). Hidden tabs are still in the form, so every field posts.
          router.post(routes.profile_submit(), new FormData(form), {
            preserveScroll: true,
            onSuccess: () => setDirty(false),
            onFinish: () => setSubmitting(false),
          });
        }}
      >
        <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />

        {hasErrors ? (
          <div ref={summaryRef} tabIndex={-1} className="outline-none">
            <FormErrorSummary errors={validation} labels={ERROR_LABELS} />
          </div>
        ) : null}

        {/* Panels hide with the `hidden` attribute rather than unmounting:
            a field that is not in the DOM is a field Save would blank. */}
        <div
          role="tabpanel"
          id="panel-personal"
          aria-labelledby="tab-personal"
          hidden={tab !== "personal"}
          className="bg-card shadow-card @container rounded-(--radius-card) border p-6"
        >
          <ProfileContactSection {...sectionProps} contactMethods={contactMethods} />
          <ProfileAddressSection {...sectionProps} states={states} />
        </div>

        <div
          role="tabpanel"
          id="panel-professional"
          aria-labelledby="tab-professional"
          hidden={tab !== "professional"}
          className="bg-card shadow-card @container rounded-(--radius-card) border p-6"
        >
          <ProfileCredentialsSection
            {...sectionProps}
            states={states}
            offices={offices}
            officeEditable={editable.office}
            office={identity.office}
            licenseStatus={identity.licenseStatus}
          />
          <ProfileBiographySection
            {...sectionProps}
            languageOptions={languageOptions}
            specialtyOptions={specialtyOptions}
            maxLanguages={limits.maxLanguages}
            maxSpecialties={limits.maxSpecialties}
            bioMaxLength={limits.bioMaxLength}
          />
          <ProfileLinksSection {...sectionProps} socialPlatforms={socialPlatforms} />
        </div>

        <div
          role="tabpanel"
          id="panel-account"
          aria-labelledby="tab-account"
          hidden={tab !== "account"}
          className="grid items-start gap-6 lg:grid-cols-2"
        >
          <ProfileIdentityPanel identity={identity} helpUrl={shell.help.url} />
          <ProfileAdministrativePanel administrative={identity.administrative} />
        </div>

        {tab === "account" && !dirty ? null : (
          <div className="sticky bottom-4 z-10">
            <FormActionBar
              status={
                submitting ? (
                  "Saving your changes…"
                ) : dirty ? (
                  <span className="flex items-center gap-2">
                    <span className="bg-warning size-2 rounded-full" aria-hidden />
                    You have unsaved changes.
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <CheckCircle2 className="text-success size-4" aria-hidden />
                    All changes saved.
                  </span>
                )
              }
            >
              <Button type="submit" disabled={submitting}>
                {submitting ? "Saving…" : "Save changes"}
              </Button>
            </FormActionBar>
          </div>
        )}
      </form>
    </div>
  );
}

Profile.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Your profile",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Your profile", href: routes.profile() },
        ],
      },
    },
  ] as const;
