# Generated manually for deterministic backfill of Office metadata.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def backfill_office_identity_and_region(apps, schema_editor):
    Office = apps.get_model("user", "Office")

    def nearest_region(office):
        if office.kind == "head_office":
            return None
        if office.kind == "region":
            return office
        node = office.parent
        seen = set()
        while node is not None and node.pk not in seen:
            seen.add(node.pk)
            if node.kind == "region":
                return node
            node = node.parent
        return None

    for office in Office.objects.select_related("parent").all():
        office.stable_key = office.slug
        region = nearest_region(office)
        office.region_id = region.pk if region else None
        office.save(update_fields=["stable_key", "region"])


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0007_alter_user_headshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="office",
            name="access_instructions",
            field=models.TextField(blank=True, verbose_name="access instructions"),
        ),
        migrations.AddField(
            model_name="office",
            name="access_instructions_internal",
            field=models.BooleanField(
                default=True, verbose_name="access instructions are internal"
            ),
        ),
        migrations.AddField(
            model_name="office",
            name="city",
            field=models.CharField(blank=True, max_length=100, verbose_name="city"),
        ),
        migrations.AddField(
            model_name="office",
            name="created_at",
            field=models.DateTimeField(
                default=django.utils.timezone.now, verbose_name="created at"
            ),
        ),
        migrations.AddField(
            model_name="office",
            name="internal_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="internal email"),
        ),
        migrations.AddField(
            model_name="office",
            name="main_phone",
            field=models.CharField(blank=True, max_length=30, verbose_name="main phone"),
        ),
        migrations.AddField(
            model_name="office",
            name="office_hours",
            field=models.JSONField(blank=True, default=list, verbose_name="office hours"),
        ),
        migrations.AddField(
            model_name="office",
            name="parking_instructions",
            field=models.TextField(blank=True, verbose_name="parking instructions"),
        ),
        migrations.AddField(
            model_name="office",
            name="public_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="public email"),
        ),
        migrations.AddField(
            model_name="office",
            name="region",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="region_offices",
                to="user.office",
                verbose_name="region",
            ),
        ),
        migrations.AddField(
            model_name="office",
            name="stable_key",
            field=models.SlugField(
                blank=True,
                db_index=False,
                max_length=80,
                null=True,
                verbose_name="stable key",
            ),
        ),
        migrations.AddField(
            model_name="office",
            name="state",
            field=models.CharField(
                blank=True,
                choices=[
                    ("AL", "Alabama"),
                    ("AK", "Alaska"),
                    ("AZ", "Arizona"),
                    ("AR", "Arkansas"),
                    ("CA", "California"),
                    ("CO", "Colorado"),
                    ("CT", "Connecticut"),
                    ("DC", "District of Columbia"),
                    ("DE", "Delaware"),
                    ("FL", "Florida"),
                    ("GA", "Georgia"),
                    ("HI", "Hawaii"),
                    ("ID", "Idaho"),
                    ("IL", "Illinois"),
                    ("IN", "Indiana"),
                    ("IA", "Iowa"),
                    ("KS", "Kansas"),
                    ("KY", "Kentucky"),
                    ("LA", "Louisiana"),
                    ("ME", "Maine"),
                    ("MD", "Maryland"),
                    ("MA", "Massachusetts"),
                    ("MI", "Michigan"),
                    ("MN", "Minnesota"),
                    ("MS", "Mississippi"),
                    ("MO", "Missouri"),
                    ("MT", "Montana"),
                    ("NE", "Nebraska"),
                    ("NV", "Nevada"),
                    ("NH", "New Hampshire"),
                    ("NJ", "New Jersey"),
                    ("NM", "New Mexico"),
                    ("NY", "New York"),
                    ("NC", "North Carolina"),
                    ("ND", "North Dakota"),
                    ("OH", "Ohio"),
                    ("OK", "Oklahoma"),
                    ("OR", "Oregon"),
                    ("PA", "Pennsylvania"),
                    ("RI", "Rhode Island"),
                    ("SC", "South Carolina"),
                    ("SD", "South Dakota"),
                    ("TN", "Tennessee"),
                    ("TX", "Texas"),
                    ("UT", "Utah"),
                    ("VT", "Vermont"),
                    ("VA", "Virginia"),
                    ("WA", "Washington"),
                    ("WV", "West Virginia"),
                    ("WI", "Wisconsin"),
                    ("WY", "Wyoming"),
                ],
                max_length=2,
                verbose_name="state",
            ),
        ),
        migrations.AddField(
            model_name="office",
            name="street_address",
            field=models.CharField(blank=True, max_length=255, verbose_name="street address"),
        ),
        migrations.AddField(
            model_name="office",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True, default=django.utils.timezone.now, verbose_name="updated at"
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="office",
            name="zip_code",
            field=models.CharField(blank=True, max_length=10, verbose_name="ZIP code"),
        ),
        migrations.CreateModel(
            name="OfficeContactAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assignment_type", models.CharField(choices=[("manager", "Manager"), ("admin", "Admin"), ("broker_contact", "Broker contact")], max_length=32, verbose_name="assignment type")),
                ("is_primary", models.BooleanField(default=False, verbose_name="primary")),
                ("starts_at", models.DateField(blank=True, null=True, verbose_name="starts at")),
                ("ends_at", models.DateField(blank=True, null=True, verbose_name="ends at")),
                ("office", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contact_assignments", to="user.office", verbose_name="office")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="office_contact_assignments", to="user.user", verbose_name="user")),
            ],
            options={
                "verbose_name": "office contact assignment",
                "verbose_name_plural": "office contact assignments",
                "ordering": ["assignment_type", "-is_primary", "user__email"],
            },
        ),
        migrations.RunPython(backfill_office_identity_and_region, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="office",
            name="stable_key",
            field=models.SlugField(max_length=80, unique=True, verbose_name="stable key"),
        ),
        migrations.AddIndex(
            model_name="office",
            index=models.Index(
                fields=["is_active", "is_assignable"],
                name="user_office_active_assignable",
            ),
        ),
        migrations.AddIndex(
            model_name="office",
            index=models.Index(
                fields=["region", "is_active"],
                name="user_office_region_active",
            ),
        ),
        migrations.AddConstraint(
            model_name="officecontactassignment",
            constraint=models.UniqueConstraint(
                fields=("office", "user", "assignment_type"),
                name="user_office_contact_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="officecontactassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_primary", True)),
                fields=("office", "assignment_type"),
                name="user_office_contact_primary_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="officecontactassignment",
            index=models.Index(
                fields=["office", "assignment_type"],
                name="user_office_contact_type",
            ),
        ),
    ]
