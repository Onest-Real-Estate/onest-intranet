"""Schedule daily policy acknowledgement reminders."""

from django.db import migrations


def create_periodic_task(apps, schema_editor):
    interval_schedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    periodic_task = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _created = interval_schedule.objects.get_or_create(
        every=1,
        period="days",
    )
    periodic_task.objects.get_or_create(
        name="compliance.send_policy_ack_reminders",
        defaults={
            "task": "apps.compliance.tasks.send_policy_ack_reminders",
            "interval_id": schedule.pk,
            "enabled": True,
        },
    )


def remove_periodic_task(apps, schema_editor):
    periodic_task = apps.get_model("django_celery_beat", "PeriodicTask")
    periodic_task.objects.filter(
        name="compliance.send_policy_ack_reminders"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0003_acknowledgement_evidence_and_corrections"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
