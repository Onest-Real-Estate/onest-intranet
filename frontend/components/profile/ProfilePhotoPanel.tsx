import { Trash2 } from "lucide-react";
import { useState } from "react";

import {
  FileUploader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
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
 */
export function ProfilePhotoPanel({
  headshotUrl,
  displayName,
  csrfToken,
  limits,
}: {
  headshotUrl: string | null;
  displayName: string;
  csrfToken: string;
  limits: ProfileLimits;
}) {
  const [photoUrl, setPhotoUrl] = useState(headshotUrl);
  // Bumped only on removal, to clear the uploader's "complete" state. Keying on
  // the photo URL instead would remount away the feedback for a fresh upload.
  const [uploaderKey, setUploaderKey] = useState(0);
  const [status, setStatus] = useState("");
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const maxMb = Math.round(limits.headshotMaxBytes / 1024 / 1024);

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
      setPhotoUrl(null);
      setUploaderKey((current) => current + 1);
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
    <SurfaceCard>
      <PanelHeader
        title="Profile photo"
        description="Saved as soon as it uploads — you do not need to press Save changes."
      />
      <SurfaceCardContent className="grid gap-4">
        <div className="flex items-center gap-4">
          <Avatar className="size-16">
            {photoUrl ? <AvatarImage src={photoUrl} alt="" /> : null}
            <AvatarFallback>{initials(displayName)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="text-sm font-medium">{displayName}</p>
            <p className="text-muted-foreground text-sm">
              {photoUrl ? "Photo on file" : "No photo yet"}
            </p>
          </div>
        </div>

        <FileUploader
          key={uploaderKey}
          label={photoUrl ? "Replace profile photo" : "Add profile photo"}
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
            setPhotoUrl(payload.url);
            setStatus("Profile photo updated.");
            return {
              name: file.name,
              url: payload.url,
              size: file.size,
              type: file.type,
            };
          }}
        />

        {photoUrl ? (
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
        <p aria-live="polite" className="sr-only">
          {status}
        </p>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
