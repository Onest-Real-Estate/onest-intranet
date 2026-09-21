import json
from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.user.models import Office, User
from apps.user.services.onboarding_metrics import journey_health
from apps.user.services.onboarding_state import new_agent_filter


class Command(BaseCommand):
    help = (
        "Print aggregate first-login onboarding health as JSON. Output holds "
        "counts, medians, and stable codes only - never names, emails, profile "
        "values, or notes - so it is safe to paste into a support ticket."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--office",
            help="Limit to one office by stable key (for example fairfax-va).",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        population = User.objects.filter(new_agent_filter(now)).distinct()
        office_key = options.get("office")
        if office_key:
            if not Office.objects.filter(stable_key=office_key).exists():
                raise CommandError("Unknown office stable key.")
            population = population.filter(office__stable_key=office_key)
        health = asdict(journey_health(population, now=now))
        health["as_of"] = health["as_of"].isoformat()
        self.stdout.write(json.dumps(health, indent=2))
