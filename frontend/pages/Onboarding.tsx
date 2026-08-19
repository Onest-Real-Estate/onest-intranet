import { Head, usePage } from "@inertiajs/react";
import {
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  IdCard,
  MapPin,
  User2,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { AuthLayout } from "@/components/AuthLayout";
import {
  FileUploader,
  FormErrorSummary,
  type UploadedFile,
} from "@/components/design-system";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { routes } from "@/lib/routes";
import type { OnboardingPageProps, OnboardingProfileValues } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FormValues = Omit<OnboardingProfileValues, "headshotUrl">;

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

const STEPS = [
  { id: "personal", label: "Personal", icon: User2 },
  { id: "address", label: "Address", icon: MapPin },
  { id: "office", label: "Office", icon: Building2 },
  { id: "review", label: "Review", icon: CheckCircle2 },
] as const;

type StepId = (typeof STEPS)[number]["id"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-destructive text-sm" role="alert">
      {message}
    </p>
  );
}

function describedBy(field: string, errors: Record<string, string | undefined>) {
  return errors[field] ? `${field}_error` : undefined;
}

// ---------------------------------------------------------------------------
// Headshot uploader
// ---------------------------------------------------------------------------

function HeadshotUploader({
  initialUrl,
  csrfToken,
  onUploaded,
  error,
}: {
  initialUrl: string | null;
  csrfToken: string;
  onUploaded: (url: string) => void;
  error?: string;
}) {
  const initialFile: UploadedFile | null = initialUrl
    ? { name: "Current profile photo", url: initialUrl, type: "image" }
    : null;
  return (
    <div className="grid gap-2">
      <FileUploader
        label="Add profile photo"
        description="JPEG or PNG · at least 200×200 px · max 5 MB"
        accept="image/jpeg,image/png"
        maxSize={5 * 1024 * 1024}
        value={initialFile}
        removable={false}
        validate={(file) =>
          ["image/jpeg", "image/png"].includes(file.type)
            ? null
            : "Choose a JPEG or PNG image. The server will verify its contents."
        }
        upload={async (file, { signal, onProgress }) => {
          const formData = new FormData();
          formData.append("headshot", file);
          formData.append("csrfmiddlewaretoken", csrfToken);
          onProgress(20);
          const response = await fetch(routes.headshot_upload(), {
            method: "POST",
            body: formData,
            signal,
          });
          const payload = (await response.json()) as {
            error?: string;
            url?: string;
          };
          if (!response.ok) {
            throw new Error(payload.error ?? "Upload failed. Please try again.");
          }
          if (!payload.url) {
            throw new Error("The server did not return an uploaded file URL.");
          }
          onProgress(100);
          onUploaded(payload.url);
          return {
            name: file.name,
            url: payload.url,
            size: file.size,
            type: file.type,
          };
        }}
      />
      {error ? (
        <p className="text-destructive text-center text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress bar
// ---------------------------------------------------------------------------

function StepProgress({ steps, current }: { steps: typeof STEPS; current: StepId }) {
  const currentIdx = steps.findIndex((s) => s.id === current);
  return (
    <nav aria-label="Onboarding progress" className="mb-6">
      <ol className="flex items-center gap-0">
        {steps.map((step, idx) => {
          const Icon = step.icon;
          const done = idx < currentIdx;
          const active = idx === currentIdx;
          return (
            <li key={step.id} className="flex flex-1 items-center">
              <div className="flex flex-col items-center gap-1">
                <div
                  className={[
                    "flex size-8 items-center justify-center rounded-full border-2 transition-colors",
                    done
                      ? "border-primary bg-primary text-primary-foreground"
                      : active
                        ? "border-primary bg-background text-primary"
                        : "border-muted bg-background text-muted-foreground",
                  ].join(" ")}
                  aria-current={active ? "step" : undefined}
                >
                  <Icon className="size-4" strokeWidth={1.5} aria-hidden />
                </div>
                <span
                  className={[
                    "hidden text-xs sm:block",
                    active ? "font-medium text-primary" : "text-muted-foreground",
                  ].join(" ")}
                >
                  {step.label}
                </span>
              </div>
              {idx < steps.length - 1 && (
                <div
                  className={[
                    "mx-1 h-0.5 flex-1 transition-colors",
                    done ? "bg-primary" : "bg-muted",
                  ].join(" ")}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Onboarding() {
  const { csrfToken, initial, validation, offices, states } =
    usePage<OnboardingPageProps>().props;
  const errors = Object.fromEntries(
    Object.entries(validation.fields).map(([field, messages]) => [field, messages[0]]),
  ) as Record<string, string | undefined>;

  const [step, setStep] = useState<StepId>(
    // If there are server-side errors, jump to the relevant step.
    errors.first_name || errors.last_name || errors.phone_number || errors.headshot
      ? "personal"
      : errors.street_address || errors.city || errors.state || errors.zip_code
        ? "address"
        : errors.office
          ? "office"
          : "personal",
  );

  const [values, setValues] = useState<FormValues>({
    firstName: initial.firstName,
    lastName: initial.lastName,
    phoneNumber: initial.phoneNumber,
    streetAddress: initial.streetAddress,
    city: initial.city,
    state: initial.state,
    zipCode: initial.zipCode,
    officeId: initial.officeId,
    mlsNumber: initial.mlsNumber,
    nrdsNumber: initial.nrdsNumber,
  });

  const [headshotUrl, setHeadshotUrl] = useState<string | null>(initial.headshotUrl);

  // Warn before abandoning form if any field is touched.
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (dirty) {
        e.preventDefault();
      }
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  function set(field: keyof FormValues, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
    setDirty(true);
  }

  const currentIdx = STEPS.findIndex((s) => s.id === step);

  function goBack() {
    if (currentIdx > 0) {
      setStep(STEPS[currentIdx - 1].id);
    }
  }

  function goNext() {
    if (currentIdx < STEPS.length - 1) {
      setStep(STEPS[currentIdx + 1].id);
    }
  }

  // Find office display name for review step.
  const selectedOffice = offices
    .flatMap((g) => g.offices)
    .find((o) => String(o.id) === values.officeId);

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-10">
      <Head title="Complete your profile" />
      <div className="w-full max-w-xl">
        <StepProgress steps={STEPS} current={step} />

        <Card>
          <CardHeader>
            <CardTitle asChild className="flex items-center gap-2">
              <h1>
                <IdCard className="size-5" strokeWidth={1.5} aria-hidden />
                Complete your profile
              </h1>
            </CardTitle>
            <CardDescription>
              {step === "personal" &&
                "Add your photo and confirm your personal details."}
              {step === "address" && "Enter your home or office address."}
              {step === "office" &&
                "Select the ONEST office you work from. MLS and NRDS numbers are optional."}
              {step === "review" && "Review your details before submitting."}
            </CardDescription>
          </CardHeader>

          <form
            id="onboarding-form"
            method="post"
            action={routes.onboarding_submit()}
            encType="multipart/form-data"
            onSubmit={() => setDirty(false)}
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />

            {/* Hidden inputs for all fields — always submitted regardless of step */}
            <input type="hidden" name="first_name" value={values.firstName} />
            <input type="hidden" name="last_name" value={values.lastName} />
            <input type="hidden" name="phone_number" value={values.phoneNumber} />
            <input type="hidden" name="street_address" value={values.streetAddress} />
            <input type="hidden" name="city" value={values.city} />
            <input type="hidden" name="state" value={values.state} />
            <input type="hidden" name="zip_code" value={values.zipCode} />
            <input type="hidden" name="office" value={values.officeId} />
            <input type="hidden" name="mls_number" value={values.mlsNumber} />
            <input type="hidden" name="nrds_number" value={values.nrdsNumber} />

            <CardContent className="grid gap-6">
              <FormErrorSummary errors={validation} />
              {/* ── Step 1: Personal ─────────────────────────────────── */}
              {step === "personal" && (
                <div className="grid gap-6">
                  <HeadshotUploader
                    initialUrl={headshotUrl}
                    csrfToken={csrfToken}
                    onUploaded={setHeadshotUrl}
                    error={errors.headshot}
                  />

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="grid gap-2">
                      <Label htmlFor="first_name_input">
                        First name
                        {initial.firstName && (
                          <Badge variant="secondary" className="ml-2 text-xs">
                            Pre-filled
                          </Badge>
                        )}
                      </Label>
                      <Input
                        id="first_name_input"
                        value={values.firstName}
                        onChange={(e) => set("firstName", e.target.value)}
                        autoComplete="given-name"
                        aria-invalid={Boolean(errors.first_name) || undefined}
                        aria-describedby={describedBy("first_name", errors)}
                        required
                      />
                      <FieldError id="first_name_error" message={errors.first_name} />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="last_name_input">
                        Last name
                        {initial.lastName && (
                          <Badge variant="secondary" className="ml-2 text-xs">
                            Pre-filled
                          </Badge>
                        )}
                      </Label>
                      <Input
                        id="last_name_input"
                        value={values.lastName}
                        onChange={(e) => set("lastName", e.target.value)}
                        autoComplete="family-name"
                        aria-invalid={Boolean(errors.last_name) || undefined}
                        aria-describedby={describedBy("last_name", errors)}
                        required
                      />
                      <FieldError id="last_name_error" message={errors.last_name} />
                    </div>
                  </div>

                  <div className="grid gap-2">
                    <Label htmlFor="phone_number_input">Phone number</Label>
                    <Input
                      id="phone_number_input"
                      type="tel"
                      value={values.phoneNumber}
                      onChange={(e) => set("phoneNumber", e.target.value)}
                      autoComplete="tel"
                      placeholder="(202) 555-0100"
                      aria-invalid={Boolean(errors.phone_number) || undefined}
                      aria-describedby={describedBy("phone_number", errors)}
                      required
                    />
                    <FieldError id="phone_number_error" message={errors.phone_number} />
                  </div>
                </div>
              )}

              {/* ── Step 2: Address ───────────────────────────────────── */}
              {step === "address" && (
                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="street_address_input">Street address</Label>
                    <Input
                      id="street_address_input"
                      value={values.streetAddress}
                      onChange={(e) => set("streetAddress", e.target.value)}
                      autoComplete="street-address"
                      aria-invalid={Boolean(errors.street_address) || undefined}
                      aria-describedby={describedBy("street_address", errors)}
                      required
                    />
                    <FieldError
                      id="street_address_error"
                      message={errors.street_address}
                    />
                  </div>

                  <div className="grid gap-4 sm:grid-cols-6">
                    <div className="grid gap-2 sm:col-span-3">
                      <Label htmlFor="city_input">City</Label>
                      <Input
                        id="city_input"
                        value={values.city}
                        onChange={(e) => set("city", e.target.value)}
                        autoComplete="address-level2"
                        aria-invalid={Boolean(errors.city) || undefined}
                        aria-describedby={describedBy("city", errors)}
                        required
                      />
                      <FieldError id="city_error" message={errors.city} />
                    </div>
                    <div className="grid gap-2 sm:col-span-2">
                      <Label htmlFor="state_trigger">State</Label>
                      <Select
                        value={values.state || undefined}
                        onValueChange={(v) => set("state", v)}
                      >
                        <SelectTrigger
                          id="state_trigger"
                          aria-invalid={Boolean(errors.state) || undefined}
                          aria-describedby={describedBy("state", errors)}
                        >
                          <SelectValue placeholder="State" />
                        </SelectTrigger>
                        <SelectContent>
                          {states.map((opt) => (
                            <SelectItem key={opt.code} value={opt.code}>
                              {opt.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FieldError id="state_error" message={errors.state} />
                    </div>
                    <div className="grid gap-2 sm:col-span-1">
                      <Label htmlFor="zip_code_input">ZIP</Label>
                      <Input
                        id="zip_code_input"
                        value={values.zipCode}
                        onChange={(e) => set("zipCode", e.target.value)}
                        autoComplete="postal-code"
                        placeholder="12345"
                        aria-invalid={Boolean(errors.zip_code) || undefined}
                        aria-describedby={describedBy("zip_code", errors)}
                        required
                      />
                      <FieldError id="zip_code_error" message={errors.zip_code} />
                    </div>
                  </div>
                </div>
              )}

              {/* ── Step 3: Office ────────────────────────────────────── */}
              {step === "office" && (
                <div className="grid gap-6">
                  <div className="grid gap-2">
                    <Label htmlFor="office_trigger">Office location</Label>
                    {offices.length === 0 ? (
                      <p className="text-muted-foreground text-sm">
                        No active offices are available. Please contact your
                        administrator.
                      </p>
                    ) : (
                      <Select
                        value={values.officeId || undefined}
                        onValueChange={(v) => set("officeId", v)}
                      >
                        <SelectTrigger
                          id="office_trigger"
                          aria-invalid={Boolean(errors.office) || undefined}
                          aria-describedby={describedBy("office", errors)}
                        >
                          <SelectValue placeholder="Select your office" />
                        </SelectTrigger>
                        <SelectContent>
                          {offices.map((group) => (
                            <SelectGroup key={group.label}>
                              <SelectLabel>{group.label}</SelectLabel>
                              {group.offices.map((office) => (
                                <SelectItem key={office.id} value={String(office.id)}>
                                  {office.name}
                                </SelectItem>
                              ))}
                            </SelectGroup>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    <FieldError id="office_error" message={errors.office} />
                  </div>

                  <Separator />

                  <div className="grid gap-1">
                    <p className="text-sm font-medium">
                      Licenses{" "}
                      <span className="font-normal text-muted-foreground">
                        — optional
                      </span>
                    </p>
                    <p className="text-muted-foreground text-sm">
                      You can add these later from your profile page.
                    </p>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="grid gap-2">
                      <Label htmlFor="mls_number_input">MLS number</Label>
                      <Input
                        id="mls_number_input"
                        value={values.mlsNumber}
                        onChange={(e) => set("mlsNumber", e.target.value)}
                        placeholder="Optional"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="nrds_number_input">NRDS number</Label>
                      <Input
                        id="nrds_number_input"
                        value={values.nrdsNumber}
                        onChange={(e) => set("nrdsNumber", e.target.value)}
                        inputMode="numeric"
                        placeholder="Optional"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* ── Step 4: Review ────────────────────────────────────── */}
              {step === "review" && (
                <div className="grid gap-4 text-sm">
                  {headshotUrl && (
                    <div className="flex justify-center">
                      <img
                        src={headshotUrl}
                        alt="Your headshot"
                        className="size-20 rounded-full object-cover ring-2 ring-primary/20"
                      />
                    </div>
                  )}

                  <ReviewRow
                    label="Name"
                    value={`${values.firstName} ${values.lastName}`.trim()}
                  />
                  <ReviewRow label="Phone" value={values.phoneNumber} />
                  <Separator />
                  <ReviewRow
                    label="Address"
                    value={[
                      values.streetAddress,
                      values.city,
                      `${values.state} ${values.zipCode}`.trim(),
                    ]
                      .filter(Boolean)
                      .join(", ")}
                  />
                  <Separator />
                  <ReviewRow label="Office" value={selectedOffice?.name ?? "—"} />
                  {values.mlsNumber && (
                    <ReviewRow label="MLS" value={values.mlsNumber} />
                  )}
                  {values.nrdsNumber && (
                    <ReviewRow label="NRDS" value={values.nrdsNumber} />
                  )}
                </div>
              )}
            </CardContent>

            <CardFooter className="flex w-full gap-3">
              {currentIdx > 0 && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={goBack}
                  className="gap-1"
                >
                  <ChevronLeft className="size-4" strokeWidth={2} aria-hidden />
                  Back
                </Button>
              )}

              {step !== "review" ? (
                <Button type="button" onClick={goNext} className="ml-auto gap-1">
                  Next
                  <ChevronRight className="size-4" strokeWidth={2} aria-hidden />
                </Button>
              ) : (
                <Button
                  type="submit"
                  form="onboarding-form"
                  size="lg"
                  className="ml-auto"
                >
                  Complete profile
                </Button>
              )}
            </CardFooter>
          </form>
        </Card>
      </div>
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="font-medium">{value || "—"}</span>
    </div>
  );
}

Onboarding.layout = (page: ReactNode) => <AuthLayout>{page}</AuthLayout>;
