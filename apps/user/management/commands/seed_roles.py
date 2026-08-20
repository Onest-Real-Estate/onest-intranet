from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.user.roles import SEEDED_GROUPS, seed_role_groups


class Command(BaseCommand):
    help = "Seed hub role groups (Admins, Region Managers, Branch Managers, Users)."

    def handle(self, *args, **options):
        seed_role_groups()
        names = sorted(
            Group.objects.filter(name__in=SEEDED_GROUPS).values_list("name", flat=True)
        )
        self.stdout.write(self.style.SUCCESS(f"Role groups ready: {', '.join(names)}."))
