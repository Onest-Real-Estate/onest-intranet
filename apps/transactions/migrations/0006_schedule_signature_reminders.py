"""Schedule signature package reminders and expiry sweeps."""

from django.db import migrations


def create_periodic_tasks(apps, schema_editor):
    interval_schedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    periodic_task = apps.get_model("django_celery_beat", "PeriodicTask")
    daily, _ = interval_schedule.objects.get_or_create(
        every=1,
        period="days",
    )
    hourly, _ = interval_schedule.objects.get_or_create(
        every=1,
        period="hours",
    )
    periodic_task.objects.get_or_create(
        name="transactions.send_signature_package_reminders",
        defaults={
            "task": "apps.transactions.tasks.send_signature_package_reminders",
            "interval_id": daily.pk,
            "enabled": True,
        },
    )
    periodic_task.objects.get_or_create(
        name="transactions.expire_signature_packages",
        defaults={
            "task": "apps.transactions.tasks.expire_signature_packages",
            "interval_id": hourly.pk,
            "enabled": True,
        },
    )


def remove_periodic_tasks(apps, schema_editor):
    periodic_task = apps.get_model("django_celery_beat", "PeriodicTask")
    periodic_task.objects.filter(
        name__in=(
            "transactions.send_signature_package_reminders",
            "transactions.expire_signature_packages",
        )
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0005_signature_packages"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_periodic_tasks, remove_periodic_tasks),
    ]
