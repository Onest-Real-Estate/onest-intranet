import { router } from "@inertiajs/react";
import { Camera, CheckCircle2, Trash2 } from "lucide-react";
import type * as React from "react";
import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FileUploader,
} from "@/components/design-system";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { ProfileLimits } from "@/types";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/**
 * The photo saves on its own, not with the form below it.
 *
 * That is a deliberate split: an image upload needs progress and a preview,
 * and holding the bytes in the page until the user happens to press Save is
 * how people end up losing an upload to a validation error somewhere else.
 * The copy says so rather than leaving it to be discovered.
 *
 * It is also the top of the profile: the face, the name, and the facts that
 * say whose page this is, in one card. Changing the photo opens a dialog, so
 * the card stays a summary instead of a permanent drop zone.
 */
export function ProfilePhotoPanel({
  headshotUrl,
  displayName,
  csrfToken,
  limits,
  details,
  aside,
}: {
  headshotUrl: string | null;
  displayName: string;
  csrfToken: string;
  limits: ProfileLimits;
  /** Who this is — email, role, office — under the name. */
  details?: React.ReactNode;
  /** Trailing content on the card, such as the completeness figure. */
  aside?: React.ReactNode;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [photoUrl, setPhotoUrl] = useState(headshotUrl);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  // Bumped only on removal, to clear the uploader's "complete" state. Keying on
  // the photo URL instead would remount away the feedback for a fresh upload.
  const [uploaderKey, setUploaderKey] = useState(0);
  const [status, setStatus] = useState("");
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const maxMb = Math.round(limits.headshotMaxBytes / 1024 / 1024);
  const avatarSrc = localPreview ?? photoUrl;

  useEffect(() => {
    setPhotoUrl(headshotUrl);
    if (headshotUrl) {
      setLocalPreview((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
    }
  }, [headshotUrl]);

  useEffect(() => {
    return () => {
      if (localPreview) {
        URL.revokeObjectURL(localPreview);
      }
    };
  }, [localPreview]);

  function rememberLocalPreview(file: File) {
    setLocalPreview((current) => {
      if (current) {
        URL.revokeObjectURL(current);
      }
      return URL.createObjectURL(file);
    });
  }

  function clearLocalPreview() {
    setLocalPreview((current) => {
      if (current) {
        URL.revokeObjectURL(current);
      }
      return null;
    });
  }

  function syncShellPhoto(nextUrl: string | null) {
    setPhotoUrl(nextUrl);
    router.reload({ only: ["user", "initial"], showProgress: false });
  }

  async function removePhoto() {
    setRemoving(true);
    setRemoveError(null);
    try {
      const body = new FormData();
      body.append("remove", "1");
      body.append("csrfmiddlewaretoken", csrfToken);
      const response = await fetch(routes.headshot_upload(), {
        method: "POST",
        body,
      });
      if (!response.ok) {
        throw new Error("The photo could not be removed. Try again.");
      }
      clearLocalPreview();
      setUploaderKey((current) => current + 1);
      syncShellPhoto(null);
      setStatus("Profile photo removed.");
    } catch (error) {
      setRemoveError(
        error instanceof Error ? error.message : "The photo could not be removed.",
      );
    } finally {
      setRemoving(false);
    }
  }

  return (
    <section
      id="profile-photo"
      aria-label="Profile photo"
      className="bg-card shadow-card @container/hero scroll-mt-24 rounded-(--radius-card) border p-5"
    >
      {/* The layout lives one level in: a container query styles the
          container's children, never the container itself. */}
      <div className="flex flex-col gap-5 @lg/hero:flex-row @lg/hero:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <div className="relative shrink-0">
            <Avatar className="border-border size-20 border">
              {avatarSrc ? (
                <AvatarImage
                  key={avatarSrc}
                  src={avatarSrc}
                  alt=""
                  onLoadingStatusChange={(status) => {
                    if (status === "loaded" && photoUrl && localPreview) {
                      clearLocalPreview();
                    }
                  }}
                />
              ) : null}
              <AvatarFallback className="text-lg">
                {initials(displayName)}
              </AvatarFallback>
            </Avatar>
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              aria-label={avatarSrc ? "Change profile photo" : "Add profile photo"}
              className="bg-card text-foreground hover:bg-muted focus-visible:ring-ring/50 absolute -right-1 -bottom-1 grid size-8 place-items-center rounded-full border shadow-card outline-none transition-colors duration-(--motion-fast) focus-visible:ring-[3px]"
            >
              <Camera className="size-4" aria-hidden />
            </button>
          </div>
          <div className="grid min-w-0 gap-1">
            <p className="truncate text-lg leading-6 font-semibold tracking-[-0.01em]">
              {displayName}
            </p>
            {details ? (
              <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                {details}
              </div>
            ) : null}
            <p
              className={cn(
                "inline-flex items-center gap-1.5 text-xs font-medium",
                avatarSrc ? "text-success" : "text-muted-foreground",
              )}
            >
              {avatarSrc ? (
                <>
                  <CheckCircle2 className="size-3.5" aria-hidden />
                  Photo on file
                </>
              ) : (
                "No photo yet — agents recognise a face faster than a name"
              )}
            </p>
          </div>
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {avatarSrc ? "Change your photo" : "Add your photo"}
            </DialogTitle>
            <DialogDescription>
              Saved as soon as it uploads — you do not need to press Save changes.
            </DialogDescription>
          </DialogHeader>
          <FileUploader
            key={uploaderKey}
            label={avatarSrc ? "Replace profile photo" : "Add profile photo"}
            description={`JPEG or PNG · at least ${limits.headshotMinDimension}×${limits.headshotMinDimension} px · max ${maxMb} MB`}
            accept="image/jpeg,image/png"
            maxSize={limits.headshotMaxBytes}
            removable={false}
            validate={(file) =>
              ["image/jpeg", "image/png"].includes(file.type)
                ? null
                : "Choose a JPEG or PNG image. The server will verify its contents."
            }
            upload={async (file, { signal, onProgress }) => {
              const body = new FormData();
              body.append("headshot", file);
              body.append("csrfmiddlewaretoken", csrfToken);
              onProgress(20);
              const response = await fetch(routes.headshot_upload(), {
                method: "POST",
                body,
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
              rememberLocalPreview(file);
              syncShellPhoto(payload.url);
              setStatus("Profile photo updated.");
              return {
                name: file.name,
                url: payload.url,
                size: file.size,
                type: file.type,
              };
            }}
          />
          {avatarSrc ? (
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={removePhoto}
                disabled={removing}
              >
                <Trash2 className="size-4" aria-hidden />
                {removing ? "Removing…" : "Remove photo"}
              </Button>
            </div>
          ) : null}
          {removeError ? (
            <p role="alert" className="text-destructive text-sm">
              {removeError}
            </p>
          ) : null}
        </DialogContent>
      </Dialog>
      <p aria-live="polite" className="sr-only">
        {status}
      </p>
    </section>
  );
}
