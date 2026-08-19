import { Head, usePage } from "@inertiajs/react";
import type { ReactNode } from "react";
import {
  FormErrorSummary,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardFooter,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import {
  type OfficeGroup,
  ProfileFormFields,
  type ProfileFormValues,
  type StateOption,
} from "@/components/ProfileFormFields";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

interface ProfilePageProps extends PageProps {
  initial: ProfileFormValues;
  validation: ValidationErrors;
  offices: OfficeGroup[];
  states: StateOption[];
}

/**
 * Profile edit — same fields as onboarding, including optional MLS / NRDS.
 */
export default function Profile() {
  const { csrfToken, initial, validation, offices, states } =
    usePage<ProfilePageProps>().props;

  return (
    // One column, one width: the page header sits directly above the form it
    // introduces rather than floating out at the page gutter.
    <div className="mx-auto grid w-full max-w-2xl gap-6 px-4 py-8 sm:px-6 lg:py-10">
      <Head title="Your profile" />
      <PageHeader
        title="Your profile"
        description="Keep your contact details, office, and license information current."
      />
      {/* No card heading: the page header above already names this form, and
          repeating the title inside the only card on the page is noise. */}
      <SurfaceCard>
        <SurfaceCardContent>
          <form
            id="profile-form"
            method="post"
            action={routes.profile_submit()}
            className="grid gap-6"
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <FormErrorSummary errors={validation} />
            <ProfileFormFields
              initial={initial}
              validation={validation}
              offices={offices}
              states={states}
            />
          </form>
        </SurfaceCardContent>
        <SurfaceCardFooter className="justify-end border-t pt-5">
          <Button type="submit" form="profile-form">
            Save changes
          </Button>
        </SurfaceCardFooter>
      </SurfaceCard>
    </div>
  );
}

Profile.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
