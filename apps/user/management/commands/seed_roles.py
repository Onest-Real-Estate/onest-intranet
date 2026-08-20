from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.user.roles import REQUIRED_ROLE_CODES, seed_brokerage_roles


class Command(BaseCommand):
    help = (
        "Idempotently seed the brokerage role catalog, Django groups, and "
        "default permission bundles."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-presentation",
            action="store_true",
            help=(
                "Overwrite display names and descriptions from the code catalog. "
                "By default existing presentation text is preserved."
            ),
        )
        parser.add_argument(
            "--skip-permissions",
            action="store_true",
            help="Do not add default permission bundles to role groups.",
        )

    def handle(self, *args, **options):
        touched = seed_brokerage_roles(
            sync_presentation=options["sync_presentation"],
            sync_permissions=not options["skip_permissions"],
        )
        from apps.user.models import BrokerageRole

        codes = set(BrokerageRole.objects.values_list("code", flat=True))
        missing = REQUIRED_ROLE_CODES - codes
        if missing:
            raise SystemExit(f"Missing role codes after seed: {sorted(missing)}")
        groups = sorted(
            Group.objects.filter(
                name__in=BrokerageRole.objects.values_list("group_name", flat=True)
            ).values_list("name", flat=True)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Brokerage roles ready ({len(codes)}). "
                f"Touched: {', '.join(touched) or 'none'}. "
                f"Groups: {', '.join(groups)}."
            )
        )
