import { Head, usePage } from "@inertiajs/react";
import {
  Building2,
  Camera,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  IdCard,
  Loader2,
  MapPin,
  User2,
} from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { AuthLayout } from "@/components/AuthLayout";
import type { OfficeGroup, StateOption } from "@/components/ProfileFormFields";
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
import { validateUsPhone, validateUsZip } from "@/lib/us-validation";
import type { PageProps } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OnboardingPageProps extends PageProps {
  initial: {
    firstName: string;
    lastName: string;
    phoneNumber: string;
    streetAddress: string;
    city: string;
    state: string;
    zipCode: string;
    officeId: string;
    mlsNumber: string;
    nrdsNumber: string;
    headshotUrl: string | null;
  };
  errors: Record<string, string>;
  offices: OfficeGroup[];
  states: StateOption[];
}

interface FormValues {
  firstName: string;
  lastName: string;
  phoneNumber: string;
  streetAddress: string;
  city: string;
  state: string;
  zipCode: string;
  officeId: string;
  mlsNumber: string;
  nrdsNumber: string;
}

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

function describedBy(field: string, errors: Record<string, string>) {
  return errors[field] ? `${field}_error` : undefined;
}

function resolveStepFromErrors(errors: Record<string, string>): StepId | null {
  if (errors.first_name || errors.last_name || errors.phone_number || errors.headshot) {
    return "personal";
  }
  if (errors.street_address || errors.city || errors.state || errors.zip_code) {
    return "address";
  }
  if (errors.office) {
    return "office";
  }
  return null;
}

function validatePersonalStep(values: FormValues): Record<string, string> {
  const next: Record<string, string> = {};
  if (!values.firstName.trim()) {
    next.first_name = "Enter a first name.";
  }
  if (!values.lastName.trim()) {
    next.last_name = "Enter a last name.";
  }
  const phoneError = validateUsPhone(values.phoneNumber);
  if (phoneError) {
    next.phone_number = phoneError;
  }
  return next;
}

function validateAddressStep(values: FormValues): Record<string, string> {
  const next: Record<string, string> = {};
  if (!values.streetAddress.trim()) {
    next.street_address = "Enter a street address.";
  }
  if (!values.city.trim()) {
    next.city = "Enter a city.";
  }
  if (!values.state) {
    next.state = "Select a state.";
  }
  const zipError = validateUsZip(values.zipCode);
  if (zipError) {
    next.zip_code = zipError;
  }
  return next;
}

function validateOfficeStep(values: FormValues): Record<string, string> {
  if (!values.officeId) {
    return { office: "Select your office." };
  }
  return {};
}

const CLIENT_ERROR_FIELDS: Partial<Record<keyof FormValues, string>> = {
  firstName: "first_name",
  lastName: "last_name",
  phoneNumber: "phone_number",
  streetAddress: "street_address",
  city: "city",
  state: "state",
  zipCode: "zip_code",
  officeId: "office",
};

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
  onUploaded: (serverUrl: string, previewUrl: string) => void;
  error?: string;
}) {
  const [preview, setPreview] = useState<string | null>(initialUrl);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const localPreviewRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (localPreviewRef.current) {
        URL.revokeObjectURL(localPreviewRef.current);
      }
    };
  }, []);

  function clearLocalPreview() {
    if (localPreviewRef.current) {
      URL.revokeObjectURL(localPreviewRef.current);
      localPreviewRef.current = null;
    }
  }

  async function handleFile(file: File) {
    setUploadError(null);
    clearLocalPreview();
    const localUrl = URL.createObjectURL(file);
    localPreviewRef.current = localUrl;
    setPreview(localUrl);
    setUploading(true);
    const fd = new FormData();
    fd.append("headshot", file);
    fd.append("csrfmiddlewaretoken", csrfToken);
    try {
      const res = await fetch(routes.headshot_upload(), {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: {
          "X-XSRF-TOKEN": csrfToken,
        },
      });
      const json = (await res.json()) as { url?: string; error?: string };
      if (!res.ok || !json.url) {
        clearLocalPreview();
        setPreview(initialUrl);
        setUploadError(json.error ?? "Upload failed. Please try again.");
      } else {
        // Keep the blob preview — it is reliable in-session. Persist the
        // server URL separately for the review step and reloads.
        onUploaded(json.url, localUrl);
      }
    } catch {
      clearLocalPreview();
      setPreview(initialUrl);
      setUploadError("Network error. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  function handlePreviewError() {
    if (preview?.startsWith("blob:")) {
      return;
    }
    setPreview(null);
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <button
        type="button"
        className="group relative size-32 cursor-pointer overflow-hidden rounded-full border-2 border-dashed border-muted-foreground/40 bg-muted transition hover:border-primary"
        onClick={() => inputRef.current?.click()}
        aria-label="Upload profile photo"
      >
        {preview ? (
          <img
            src={preview}
            alt=""
            className="size-full object-cover"
            onError={handlePreviewError}
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-1 text-muted-foreground">
            <Camera className="size-8" strokeWidth={1.5} aria-hidden />
            <span className="text-xs">Add photo</span>
          </div>
        )}
        {uploading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/60">
            <Loader2 className="size-6 animate-spin text-primary" aria-hidden />
          </div>
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition group-hover:opacity-100">
          <Camera className="size-6 text-white" strokeWidth={1.5} aria-hidden />
        </div>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png"
        className="sr-only"
        aria-label="Select profile photo"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />

      {(uploadError || error) && (
        <p className="text-destructive text-center text-sm" role="alert">
          {uploadError ?? error}
        </p>
      )}

      {!uploading && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => inputRef.current?.click()}
        >
          {preview ? "Replace photo" : "Choose photo"}
        </Button>
      )}

      <p className="text-muted-foreground text-center text-xs">
        JPEG or PNG · at least 200×200 px · max 5 MB
      </p>
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
  const { csrfToken, initial, errors, offices, states } =
    usePage<OnboardingPageProps>().props;

  const [step, setStep] = useState<StepId>(resolveStepFromErrors(errors) ?? "personal");

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

  const [headshotPreviewUrl, setHeadshotPreviewUrl] = useState<string | null>(
    initial.headshotUrl,
  );
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const fieldErrors = { ...clientErrors, ...errors };

  useEffect(() => {
    const stepFromErrors = resolveStepFromErrors(errors);
    if (stepFromErrors) {
      setStep(stepFromErrors);
    }
  }, [errors]);

  useEffect(() => {
    if (Object.keys(errors).length === 0) {
      return;
    }
    setValues({
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
    setHeadshotPreviewUrl(initial.headshotUrl);
    setClientErrors({});
  }, [errors, initial]);

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
    const errorField = CLIENT_ERROR_FIELDS[field];
    if (!errorField) {
      return;
    }
    setClientErrors((prev) => {
      if (!prev[errorField]) {
        return prev;
      }
      const next = { ...prev };
      delete next[errorField];
      return next;
    });
  }

  const currentIdx = STEPS.findIndex((s) => s.id === step);

  function goBack() {
    if (currentIdx > 0) {
      setClientErrors({});
      setStep(STEPS[currentIdx - 1].id);
    }
  }

  function goNext() {
    let stepErrors: Record<string, string> = {};
    if (step === "personal") {
      stepErrors = validatePersonalStep(values);
    } else if (step === "address") {
      stepErrors = validateAddressStep(values);
    } else if (step === "office") {
      stepErrors = validateOfficeStep(values);
    }

    if (Object.keys(stepErrors).length > 0) {
      setClientErrors(stepErrors);
      return;
    }

    setClientErrors({});
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
              {/* ── Step 1: Personal ─────────────────────────────────── */}
              {step === "personal" && (
                <div className="grid gap-6">
                  <HeadshotUploader
                    initialUrl={initial.headshotUrl}
                    csrfToken={csrfToken}
                    onUploaded={(_serverUrl, previewUrl) => {
                      setHeadshotPreviewUrl(previewUrl);
                    }}
                    error={fieldErrors.headshot}
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
                        aria-invalid={Boolean(fieldErrors.first_name) || undefined}
                        aria-describedby={describedBy("first_name", fieldErrors)}
                        required
                      />
                      <FieldError
                        id="first_name_error"
                        message={fieldErrors.first_name}
                      />
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
                        aria-invalid={Boolean(fieldErrors.last_name) || undefined}
                        aria-describedby={describedBy("last_name", fieldErrors)}
                        required
                      />
                      <FieldError
                        id="last_name_error"
                        message={fieldErrors.last_name}
                      />
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
                      aria-invalid={Boolean(fieldErrors.phone_number) || undefined}
                      aria-describedby={describedBy("phone_number", fieldErrors)}
                      required
                    />
                    <FieldError
                      id="phone_number_error"
                      message={fieldErrors.phone_number}
                    />
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
                      aria-invalid={Boolean(fieldErrors.street_address) || undefined}
                      aria-describedby={describedBy("street_address", fieldErrors)}
                      required
                    />
                    <FieldError
                      id="street_address_error"
                      message={fieldErrors.street_address}
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
                        aria-invalid={Boolean(fieldErrors.city) || undefined}
                        aria-describedby={describedBy("city", fieldErrors)}
                        required
                      />
                      <FieldError id="city_error" message={fieldErrors.city} />
                    </div>
                    <div className="grid gap-2 sm:col-span-2">
                      <Label htmlFor="state_trigger">State</Label>
                      <Select
                        value={values.state || undefined}
                        onValueChange={(v) => set("state", v)}
                      >
                        <SelectTrigger
                          id="state_trigger"
                          aria-invalid={Boolean(fieldErrors.state) || undefined}
                          aria-describedby={describedBy("state", fieldErrors)}
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
                      <FieldError id="state_error" message={fieldErrors.state} />
                    </div>
                    <div className="grid gap-2 sm:col-span-2">
                      <Label htmlFor="zip_code_input">ZIP</Label>
                      <Input
                        id="zip_code_input"
                        value={values.zipCode}
                        onChange={(e) => set("zipCode", e.target.value)}
                        autoComplete="postal-code"
                        placeholder="12345"
                        aria-invalid={Boolean(fieldErrors.zip_code) || undefined}
                        aria-describedby={describedBy("zip_code", fieldErrors)}
                        required
                      />
                    </div>
                  </div>
                  <FieldError id="zip_code_error" message={fieldErrors.zip_code} />
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
                          aria-invalid={Boolean(fieldErrors.office) || undefined}
                          aria-describedby={describedBy("office", fieldErrors)}
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
                    <FieldError id="office_error" message={fieldErrors.office} />
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
                  {headshotPreviewUrl && (
                    <div className="flex justify-center">
                      <img
                        src={headshotPreviewUrl}
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
