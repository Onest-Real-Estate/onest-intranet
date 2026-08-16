import { usePage } from "@inertiajs/react";
import type { ReactNode } from "react";

import { AppLayout } from "@/components/AppLayout";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { PageProps } from "@/types";

export default function Dashboard() {
  const { user } = usePage<PageProps>().props;

  // The route is login-required; this only narrows the type.
  if (!user) {
    return null;
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
      <p className="mt-2 text-muted-foreground">Welcome back, {user.name}.</p>
      <Separator className="my-6" />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Your account
            <Badge variant="secondary">Microsoft SSO</Badge>
          </CardTitle>
          <CardDescription>
            Profile details provided by Microsoft Entra ID at sign-in.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm">
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Name</span>
            <span className="font-medium">{user.name}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Email</span>
            <span className="font-medium">{user.email}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

Dashboard.layout = (page: ReactNode) => <AppLayout>{page}</AppLayout>;
