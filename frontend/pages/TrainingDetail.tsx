import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { TrainingArticle } from "@/components/training/TrainingArticle";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { TrainingDetailPageProps } from "@/types";

export default function TrainingDetail() {
  const { content } = usePage<TrainingDetailPageProps>().props;

  return (
    <>
      <Head title={content.title} />
      <div className="grid gap-8">
        <PageHeader
          title={content.title}
          description={content.summary || undefined}
          meta={
            <span className="text-muted-foreground text-sm">
              {content.category.label}
              {content.publishedAt
                ? ` · Published ${new Date(content.publishedAt).toLocaleDateString()}`
                : ""}
            </span>
          }
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.training_learning()}>
                <ArrowLeft className="size-4" aria-hidden />
                All training
              </Link>
            </Button>
          }
        />
        <TrainingArticle content={content} />
      </div>
    </>
  );
}

TrainingDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Training & learning",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Training & learning", href: routes.training_learning() },
        ],
      },
    },
  ] as const;
