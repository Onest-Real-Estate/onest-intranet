import { Link } from "@inertiajs/react";
import { CheckCircle2, CircleAlert, LoaderCircle, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Callout, FileUploader, FormFieldError } from "@/components/design-system";
import {
  HeadshotRequestError,
  removeHeadshot,
  uploadHeadshot,
} from "@/components/onboarding/profile/headshot-transport";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { OnboardingFieldPolicy, OnboardingLimits } from "@/types";

const ACCEPTED_TYPES = ["image/jpeg", "image/png"];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "?";
  }
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function objectUrl(file: File): string | null {
  return typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : null;
}

/**
 * The headshot saves on its own endpoint the moment it uploads, separately
 * from the section's text fields. That split is what lets a failed section
 * save keep the photo, and a failed upload keep everything typed beside it.
 */
export function HeadshotField({
  initialUrl,
  displayName,
  csrfToken,
  limits,
  policy,
  error,
  onPhotoChange,
}: {
  initialUrl: string | null;
  displayName: string;
  csrfToken: string;
  limits: OnboardingLimits;
  policy: OnboardingFieldPolicy;
  error?: string;
  onPhotoChange: () => void;
}) {
  const [photoUrl, setPhotoUrl] = useState(initialUrl);
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [uploaderKey, setUploaderKey] = useState(0);
  const [announcement, setAnnouncement] = useState("");
  const maxMb = Math.round(limits.headshotMaxBytes / 1024 / 1024);
  const minimum = limits.headshotMinDimension;
  const shown = preview ?? photoUrl;

  useEffect(() => {
    if (!preview) {
      return;
    }
    return () => URL.revokeObjectURL?.(preview);
  }, [preview]);

  async function remove() {
    setRemoving(true);
    setRemoveError(null);
    try {
      await removeHeadshot({ csrfToken });
      setPhotoUrl(null);
      setPreview(null);
      setUploaderKey((current) => current + 1);
      setAnnouncement("Headshot removed.");
      onPhotoChange();
    } catch (failure) {
      if (failure instanceof HeadshotRequestError && failure.sessionExpired) {
        setSessionExpired(true);
      }
      setRemoveError(
        failure instanceof Error ? failure.message : "The photo could not be removed.",
      );
    } finally {
      setRemoving(false);
    }
  }

  const describedBy = ["headshot_requirements", error ? "headshot_error" : null]
    .filter(Boolean)
    .join(" ");

  return (
    <fieldset
      id="headshot"
      tabIndex={-1}
      aria-invalid={Boolean(error) || undefined}
      aria-describedby={describedBy}
      className={cn(
        "grid gap-5 rounded-lg border p-4 outline-none sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-6 sm:p-5",
        error && "border-destructive/60",
      )}
    >
      <legend className="sr-only">
        {policy.label}
        {policy.required ? " (required)" : ""}
      </legend>

      <div className="flex flex-col items-center gap-3 sm:w-36">
        <div className="bg-background shadow-card relative rounded-full p-1">
          <Avatar className="border-border/60 size-28 border">
            {shown ? <AvatarImage key={shown} src={shown} alt="Your headshot" /> : null}
            <AvatarFallback className="text-2xl font-semibold">
              {initials(displayName)}
            </AvatarFallback>
          </Avatar>
          {uploading ? (
            <span className="bg-background/70 absolute inset-1 grid place-items-center rounded-full">
              <LoaderCircle className="text-primary size-6 animate-spin" aria-hidden />
            </span>
          ) : null}
        </div>
        <p
          className={cn(
            "inline-flex items-center gap-1.5 text-xs font-medium",
            photoUrl ? "text-success" : "text-warning-ink",
          )}
        >
          {photoUrl ? (
            <CheckCircle2 className="size-3.5" aria-hidden />
          ) : (
            <CircleAlert className="size-3.5" aria-hidden />
          )}
          {photoUrl
            ? "Photo saved"
            : policy.required
              ? "Photo required"
              : "No photo yet"}
        </p>
      </div>

      <div className="grid min-w-0 content-start gap-3">
        <div className="grid gap-1">
          <p className="flex items-center gap-1 text-sm font-semibold" aria-hidden>
            {policy.label}
            {policy.required ? <span className="text-destructive">*</span> : null}
          </p>
          <div id="headshot_requirements" className="grid gap-2">
            {policy.guidance ? (
              <p className="text-muted-foreground max-w-measure text-sm">
                {policy.guidance}
              </p>
            ) : null}
            <ul className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
              <li>JPEG or PNG</li>
              <li>
                At least {minimum}×{minimum} px
              </li>
              <li>Up to {maxMb} MB</li>
              <li>Saves as soon as it uploads</li>
            </ul>
          </div>
        </div>

        <FileUploader
          key={uploaderKey}
          label={photoUrl ? "Replace headshot" : "Upload headshot"}
          description="Drag a photo here, or press Enter to choose one"
          accept={ACCEPTED_TYPES.join(",")}
          maxSize={limits.headshotMaxBytes}
          preview={false}
          removable={false}
          validate={(file) =>
            ACCEPTED_TYPES.includes(file.type)
              ? null
              : "Choose a JPEG or PNG image. The server checks the file itself too."
          }
          upload={async (file, { signal, onProgress }) => {
            setSessionExpired(false);
            setPreview(objectUrl(file));
            setUploading(true);
            try {
              const url = await uploadHeadshot(file, { csrfToken, signal, onProgress });
              setPhotoUrl(url);
              setAnnouncement("Headshot uploaded and saved.");
              onPhotoChange();
              return { name: file.name, url, size: file.size, type: file.type };
            } catch (failure) {
              // Fall back to the photo that is actually stored.
              setPreview(null);
              if (failure instanceof HeadshotRequestError && failure.sessionExpired) {
                setSessionExpired(true);
              }
              throw failure;
            } finally {
              setUploading(false);
            }
          }}
        />

        {photoUrl ? (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground text-xs">
              You can replace or remove it until you finish setup.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void remove()}
              disabled={removing || uploading}
            >
              <Trash2 aria-hidden />
              {removing ? "Removing…" : "Remove photo"}
            </Button>
          </div>
        ) : null}

        {sessionExpired ? (
          <Callout
            tone="warning"
            role="alert"
            action={
              <Button asChild size="sm" variant="outline">
                <Link href={routes.login()}>Sign in again</Link>
              </Button>
            }
          >
            Your session expired. Sign in again to upload; the sections you saved are
            kept.
          </Callout>
        ) : null}
        <FormFieldError id="headshot_remove_error" message={removeError ?? undefined} />
        <FormFieldError id="headshot_error" message={error} />
        <p aria-live="polite" className="sr-only">
          {announcement}
        </p>
      </div>
    </fieldset>
  );
}
