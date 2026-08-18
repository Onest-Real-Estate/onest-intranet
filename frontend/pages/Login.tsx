import { Head, usePage } from "@inertiajs/react";
import { ArrowRight } from "lucide-react";

import { MicrosoftLogo } from "@/components/MicrosoftLogo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import loginHero from "@/images/loginpage.jpg";
import onestLogo from "@/images/onest.png";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

export default function Login() {
  const { csrfToken } = usePage<PageProps>().props;

  return (
    <div className="grid min-h-svh bg-[#f8f7f3] lg:grid-cols-2">
      <Head title="Sign in" />
      <aside className="relative hidden overflow-hidden lg:block">
        <img
          src={loginHero}
          alt=""
          className="absolute inset-0 size-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#1b1c18]/35 via-transparent to-[#1b1c18]/10" />
      </aside>

      <div className="flex items-center justify-center px-6 py-16 sm:px-10">
        <Card className="w-full max-w-md rounded-[14px] border-[#e9e6de] py-8 shadow-[0_4px_12px_rgba(23,23,23,0.03)]">
          <CardHeader className="items-center text-center">
            <img
              src={onestLogo}
              alt="ONEST Real Estate"
              className="mx-auto h-24 w-auto object-contain"
            />
            <CardDescription className="text-base text-[#7a7a75]">
              Sign in to your agent portal
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6">
            {/* Full page POST — the OAuth handshake redirects to Microsoft. */}
            <form method="post" action={routes.microsoft_login()}>
              <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
              <Button
                type="submit"
                size="lg"
                className="h-12 w-full rounded-lg bg-[#ddb52a] font-semibold text-[#0d0d0d] shadow-none hover:bg-[#d0aa24]"
              >
                <MicrosoftLogo className="size-5" />
                Sign in with Microsoft
                <ArrowRight className="size-4" strokeWidth={1.5} />
              </Button>
            </form>
            <div className="grid gap-4">
              <div className="bg-[#e9e6de] h-px w-full" />
              <p className="text-center text-sm text-[#7a7a75]">
                New to oNEST?{" "}
                <span className="font-semibold text-[#5a4700]">
                  Ask your broker for access.
                </span>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
