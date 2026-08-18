import { usePage } from "@inertiajs/react";
import { IdCard } from "lucide-react";
import type { ReactNode } from "react";

import { AuthLayout } from "@/components/AuthLayout";
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

interface OnboardingPageProps extends PageProps {
  initial: ProfileFormValues;
  errors: Record<string, string>;
  offices: OfficeGroup[];
  states: StateOption[];
}

/**
 * Post-signup details flow — new Microsoft SSO users are redirected here by
 * ProfileCompletionMiddleware until they submit this form (see
 * apps/user/views.auth_views.onboarding_submit). Name is pre-filled from
 * Microsoft when Graph sent it.
 */
export default function Onboarding() {
  const { csrfToken, initial, errors, offices, states } =
    usePage<OnboardingPageProps>().props;

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IdCard className="size-5" strokeWidth={1.5} />
            Complete your profile
          </CardTitle>
          <CardDescription>
            Confirm your details and pick the office you work from. MLS and NRDS numbers
            can wait until later.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            id="onboarding-form"
            method="post"
            action={routes.onboarding_submit()}
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
          <Button type="submit" form="onboarding-form" size="lg" className="w-full">
            Continue
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

Onboarding.layout = (page: ReactNode) => <AuthLayout>{page}</AuthLayout>;
