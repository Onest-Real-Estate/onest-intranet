from django.db import migrations, models


def backfill_completed_onboarding_cases(apps, schema_editor):
    User = apps.get_model("user", "User")
    UserOnboardingCase = apps.get_model("user", "UserOnboardingCase")
    for user in User.objects.filter(profile_completed=True).iterator(chunk_size=500):
        completed_at = user.profile_completed_at or user.date_joined
        case, _created = UserOnboardingCase.objects.get_or_create(user_id=user.pk)
        updates = {}
        if case.office_confirmed_at is None:
            updates["office_confirmed_at"] = completed_at
        if case.required_setup_completed_at is None:
            updates["required_setup_completed_at"] = completed_at
        if updates:
            UserOnboardingCase.objects.filter(pk=case.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0030_agent_directory_specialties"),
    ]

    operations = [
        migrations.AddField(
            model_name="useronboardingcase",
            name="office_confirmed_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "When the agent confirmed the selected office for this "
                    "onboarding cycle."
                ),
                null=True,
                verbose_name="office confirmed at",
            ),
        ),
        migrations.AddField(
            model_name="useronboardingcase",
            name="required_setup_completed_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Compatibility checkpoint releasing the strict profile and "
                    "office gate."
                ),
                null=True,
                verbose_name="required setup completed at",
            ),
        ),
        migrations.AddField(
            model_name="useronboardingcase",
            name="office_handoff_state",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("notified", "Notified"),
                    ("notification_failed", "Notification failed"),
                ],
                default="pending",
                max_length=24,
                verbose_name="office handoff state",
            ),
        ),
        migrations.AddField(
            model_name="useronboardingcase",
            name="office_handoff_updated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="office handoff updated at",
            ),
        ),
        migrations.RunPython(
            backfill_completed_onboarding_cases,
            migrations.RunPython.noop,
        ),
    ]
