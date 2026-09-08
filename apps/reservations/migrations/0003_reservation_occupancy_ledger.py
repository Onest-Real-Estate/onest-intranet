"""Unified capacity ledger for reservations and availability blocks.

Every capacity consumer — an agent booking and an administrative block alike —
gets one ``Occupancy`` row, so a single PostgreSQL exclusion constraint decides
overlap for both. Existing ``SpaceAvailabilityException`` rows are migrated onto
the ledger here; the column lands nullable, is backfilled, and only then becomes
required.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.reservations.operations import (
    AddConstraintIfPostgres,
    BtreeGistExtensionIfPostgres,
    occupancy_no_overlap_constraint,
)

EXCEPTION_SOURCE = "exception"


def backfill_exception_occupancies(apps, schema_editor):
    """Give every existing block a ledger row, refusing to hide a conflict.

    Overlapping blocks on one space were legal before this migration and are not
    after it. Rather than silently drop one side, stop with the offending spaces
    named so an operator resolves them deliberately.
    """
    Exception_ = apps.get_model("reservations", "SpaceAvailabilityException")
    Occupancy = apps.get_model("reservations", "Occupancy")
    blocks = list(
        Exception_.objects.filter(occupancy__isnull=True).order_by(
            "space_id", "starts_at", "ends_at", "pk"
        )
    )
    conflicts = []
    previous = None
    for block in blocks:
        if (
            previous is not None
            and previous.space_id == block.space_id
            and previous.ends_at > block.starts_at
        ):
            conflicts.append((block.space_id, previous.pk, block.pk))
        previous = block
    if conflicts:
        detail = ", ".join(
            f"space {space_id}: exceptions {left} and {right}"
            for space_id, left, right in conflicts
        )
        raise RuntimeError(
            "Overlapping availability exceptions cannot join the capacity "
            f"ledger. Resolve these rows first — {detail}."
        )
    for block in blocks:
        occupancy = Occupancy.objects.create(
            space_id=block.space_id,
            starts_at=block.starts_at,
            ends_at=block.ends_at,
            source=EXCEPTION_SOURCE,
            consumes_capacity=True,
        )
        block.occupancy = occupancy
        block.save(update_fields=["occupancy"])


def drop_exception_occupancies(apps, schema_editor):
    Exception_ = apps.get_model("reservations", "SpaceAvailabilityException")
    Occupancy = apps.get_model("reservations", "Occupancy")
    occupancy_ids = list(
        Exception_.objects.exclude(occupancy__isnull=True).values_list(
            "occupancy_id", flat=True
        )
    )
    Exception_.objects.update(occupancy=None)
    Occupancy.objects.filter(pk__in=occupancy_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0002_grant_space_role_permissions'),
        ('user', '0029_office_timezone'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Occupancy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('starts_at', models.DateTimeField()),
                ('ends_at', models.DateTimeField()),
                ('source', models.CharField(choices=[('reservation', 'Reservation'), ('exception', 'Availability exception')], max_length=16)),
                ('consumes_capacity', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('space', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='occupancies', to='reservations.space')),
            ],
            options={
                'ordering': ['starts_at', 'ends_at', 'pk'],
            },
        ),
        migrations.AddField(
            model_name='spaceavailabilityexception',
            name='occupancy',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='exception_record', to='reservations.occupancy'),
        ),
        migrations.CreateModel(
            name='Reservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('reference', models.CharField(max_length=24, unique=True)),
                ('office_name', models.CharField(max_length=200)),
                ('space_name', models.CharField(max_length=200)),
                ('starts_at', models.DateTimeField()),
                ('ends_at', models.DateTimeField()),
                ('buffer_before_minutes', models.PositiveIntegerField(default=0)),
                ('buffer_after_minutes', models.PositiveIntegerField(default=0)),
                ('purpose', models.CharField(max_length=240)),
                ('attendee_count', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('related_record_type', models.CharField(blank=True, max_length=64)),
                ('related_record_id', models.CharField(blank=True, max_length=64)),
                ('status', models.CharField(choices=[('requested', 'Awaiting approval'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled'), ('denied', 'Denied'), ('completed', 'Completed')], default='confirmed', max_length=16)),
                ('instructions_snapshot', models.TextField(blank=True)),
                ('submission_key', models.CharField(editable=False, max_length=64, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cancel_reason', models.CharField(blank=True, max_length=240)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='space_reservations_approved', to=settings.AUTH_USER_MODEL)),
                ('cancelled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='space_reservations_cancelled', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='space_reservations_created', to=settings.AUTH_USER_MODEL)),
                ('occupancy', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='reservation_record', to='reservations.occupancy')),
                ('office', models.ForeignKey(help_text='Owning office snapshot at reservation creation.', on_delete=django.db.models.deletion.PROTECT, related_name='space_reservations', to='user.office')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='space_reservations', to=settings.AUTH_USER_MODEL)),
                ('space', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reservations', to='reservations.space')),
            ],
            options={
                'ordering': ['-starts_at', '-pk'],
                'permissions': (('book_spaces', 'Can book active spaces at the assigned office'), ('manage_reservations', 'Can manage reservations within scope'), ('override_reservations', 'Can override reservation policy with an audited reason')),
            },
        ),
        migrations.AddIndex(
            model_name='occupancy',
            index=models.Index(fields=['space', 'consumes_capacity', 'starts_at', 'ends_at'], name='rsv_occupancy_calendar_idx'),
        ),
        migrations.AddConstraint(
            model_name='occupancy',
            constraint=models.CheckConstraint(condition=models.Q(('ends_at__gt', models.F('starts_at'))), name='rsv_occupancy_ends_after_start'),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['space', 'status', 'starts_at'], name='rsv_booking_space_state_time'),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['owner', '-starts_at'], name='rsv_booking_owner_time'),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['office', 'status', 'starts_at'], name='rsv_booking_office_state_time'),
        ),
        migrations.AddConstraint(
            model_name='reservation',
            constraint=models.CheckConstraint(condition=models.Q(('ends_at__gt', models.F('starts_at'))), name='rsv_booking_ends_after_start'),
        ),
        migrations.AddConstraint(
            model_name='reservation',
            constraint=models.CheckConstraint(condition=models.Q(('reference', ''), _negated=True), name='rsv_booking_requires_reference'),
        ),
        migrations.AddConstraint(
            model_name='reservation',
            constraint=models.CheckConstraint(condition=models.Q(('purpose', ''), _negated=True), name='rsv_booking_requires_purpose'),
        ),
        migrations.AddConstraint(
            model_name='reservation',
            constraint=models.CheckConstraint(condition=models.Q(('attendee_count__isnull', True), ('attendee_count__gte', 1), _connector='OR'), name='rsv_booking_attendees_positive'),
        ),
        migrations.AddConstraint(
            model_name='reservation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('cancelled_at__isnull', False), ('status', 'cancelled')), models.Q(models.Q(('status', 'cancelled'), _negated=True), ('cancelled_at__isnull', True)), _connector='OR'), name='rsv_booking_cancelled_at_matches'),
        ),
        migrations.RunPython(
            backfill_exception_occupancies,
            drop_exception_occupancies,
            elidable=False,
        ),
        migrations.AlterField(
            model_name='spaceavailabilityexception',
            name='occupancy',
            field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='exception_record', to='reservations.occupancy'),
        ),
        BtreeGistExtensionIfPostgres(),
        AddConstraintIfPostgres(
            model_name='occupancy',
            constraint=occupancy_no_overlap_constraint(),
        ),
    ]
