import { usePage } from "@inertiajs/react";
import type { ReactNode } from "react";

import { AppLayout } from "@/components/AppLayout";
import { MicrosoftLogo } from "@/components/MicrosoftLogo";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

export default function Login() {
  const { csrfToken } = usePage<PageProps>().props;

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            Use your Microsoft account to continue to Onest.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Full page POST — the OAuth handshake redirects to Microsoft. */}
          <form method="post" action={routes["microsoft_login"]()}>
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <Button type="submit" size="lg" className="w-full">
              <MicrosoftLogo className="size-4" />
              Continue with Microsoft
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

Login.layout = (page: ReactNode) => <AppLayout>{page}</AppLayout>;
