import { Head, usePage } from "@inertiajs/react";
import { ArrowRight, Clock3 } from "lucide-react";

import { MicrosoftLogo } from "@/components/MicrosoftLogo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import loginHero from "@/images/loginpage.jpg";
import onestLogo from "@/images/onest.png";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

interface LoginPageProps extends PageProps {
  sessionExpired: boolean;
}

export default function Login() {
  const { csrfToken, sessionExpired } = usePage<LoginPageProps>().props;

  return (
    <div className="bg-background grid min-h-svh lg:grid-cols-2">
      <Head title="Sign in" />
      {/*
        Decorative, and 2.4 MB — as an <img> every phone downloads it to render
        a panel that is hidden below `lg`. A background image on a
        `display: none` element is never fetched, so small screens skip it.
      */}
      <aside
        className="relative hidden overflow-hidden bg-cover bg-center lg:block"
        style={{ backgroundImage: `url(${loginHero})` }}
      >
        <div className="from-foreground/35 to-foreground/10 absolute inset-0 bg-gradient-to-t via-transparent" />
      </aside>

      <main className="flex items-center justify-center px-6 py-16 sm:px-10">
        <Card className="w-full max-w-md rounded-xl py-8 shadow-lg">
          <CardHeader className="items-center text-center">
            <img
              src={onestLogo}
              alt="ONEST Real Estate"
              width={153}
              height={96}
              className="mx-auto h-24 w-auto object-contain"
            />
            <h1 className="sr-only">Sign in to ONEST HUB</h1>
            <CardDescription className="text-base">
              Sign in to your agent portal
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6">
            {sessionExpired ? (
              <div
                role="status"
                className="bg-muted flex items-start gap-3 rounded-lg border px-3.5 py-3 text-left"
              >
                <Clock3 aria-hidden className="text-primary mt-0.5 size-4" />
                <div>
                  <p className="text-sm font-semibold">Your session expired</p>
                  <p className="text-muted-foreground mt-0.5 text-xs leading-5">
                    Sign in again to continue securely.
                  </p>
                </div>
              </div>
            ) : null}
            {/* Full page POST — the OAuth handshake redirects to Microsoft. */}
            <form method="post" action={routes.microsoft_login()}>
              <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
              <Button
                type="submit"
                size="lg"
                className="brand-action h-12 w-full rounded-lg font-semibold shadow-none"
              >
                <MicrosoftLogo className="size-5" />
                Sign in with Microsoft
                <ArrowRight className="size-4" strokeWidth={1.5} aria-hidden />
              </Button>
            </form>
            <div className="grid gap-4">
              <Separator />
              <p className="text-muted-foreground text-center text-sm">
                New to oNEST?{" "}
                <span className="text-primary font-semibold">
                  Ask your broker for access.
                </span>
              </p>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
