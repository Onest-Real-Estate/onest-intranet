# Generated manually for TrainingCertificate verification fields.

import uuid

from django.db import migrations, models


def _assign_public_ids(apps, schema_editor):
    TrainingCertificate = apps.get_model("training", "TrainingCertificate")
    for row in TrainingCertificate.objects.filter(public_id__isnull=True).iterator():
        row.public_id = uuid.uuid4()
        row.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0004_progress_quizzes_sessions"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingcertificate",
            name="public_id",
            field=models.UUIDField(
                editable=False,
                help_text="Opaque id embedded in the certificate QR for verification.",
                null=True,
                verbose_name="public id",
            ),
        ),
        migrations.AddField(
            model_name="trainingcertificate",
            name="signature",
            field=models.CharField(
                blank=True,
                help_text=(
                    "HMAC-SHA256 hex digest of the canonical certificate payload."
                ),
                max_length=128,
                verbose_name="signature",
            ),
        ),
        migrations.AddField(
            model_name="trainingcertificate",
            name="signature_algorithm",
            field=models.CharField(
                blank=True,
                default="",
                help_text="e.g. hmac-sha256-v1",
                max_length=32,
                verbose_name="signature algorithm",
            ),
        ),
        migrations.RunPython(_assign_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="trainingcertificate",
            name="public_id",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                help_text="Opaque id embedded in the certificate QR for verification.",
                unique=True,
                verbose_name="public id",
            ),
        ),
    ]
