import { usePage } from "@inertiajs/react";
import { UserRound } from "lucide-react";
import type { ReactNode } from "react";

import { HubLayout } from "@/components/HubLayout";
import {
  type OfficeGroup,
  ProfileFormFields,
  type ProfileFormValues,
  type StateOption,
} from "@/components/ProfileFormFields";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

interface ProfilePageProps extends PageProps {
  initial: ProfileFormValues;
  errors: Record<string, string>;
  offices: OfficeGroup[];
  states: StateOption[];
}

/**
 * Profile edit — same fields as onboarding, including optional MLS / NRDS.
 */
export default function Profile() {
  const { csrfToken, initial, errors, offices, states } =
    usePage<ProfilePageProps>().props;

  return (
    <div className="page-shell py-10">
      <Card className="mx-auto w-full max-w-xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserRound className="size-5" strokeWidth={1.5} />
            Your profile
          </CardTitle>
          <CardDescription>
            Update your contact details, office, and license numbers.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            id="profile-form"
            method="post"
            action={routes.profile_submit()}
            className="grid gap-6"
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <ProfileFormFields
              initial={initial}
              errors={errors}
              offices={offices}
              states={states}
            />
          </form>
        </CardContent>
        <CardFooter className="w-full">
          <Button type="submit" form="profile-form" size="lg" className="w-full">
            Save changes
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

Profile.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
