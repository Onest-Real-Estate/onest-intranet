import type { ReactNode } from "react";

import { AuthLayout } from "@/components/AuthLayout";
import { OnboardingProfileFlow } from "@/components/onboarding/profile/OnboardingProfileFlow";

/** First-login profile setup. The flow itself is reusable by the setup dialog. */
export default function Onboarding() {
  return (
    <div className="flex flex-1 flex-col px-4">
      <OnboardingProfileFlow />
    </div>
  );
}

Onboarding.layout = (page: ReactNode) => <AuthLayout>{page}</AuthLayout>;
