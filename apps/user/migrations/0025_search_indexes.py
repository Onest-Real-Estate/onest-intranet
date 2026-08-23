"""Full-text and trigram indexes for people, office, and resource search.

PostgreSQL-only, applied through the conditional wrappers in
``apps.web.search.operations``; SQLite takes the substring path instead.

Names and office labels get **trigram** indexes rather than full-text ones:
``ts_rank`` over a person's name is close to meaningless — there is no
document to weight — while ``fairfx`` finding Fairfax is exactly the failure
somebody hits when they half-remember a spelling.
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import migrations

from apps.web.search.operations import AddIndexIfPostgres


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0024_officeresource_archived_at_and_more"),
        # The pg_trgm extension is created by the announcements migration; the
        # dependency makes that ordering explicit rather than incidental.
        ("announcements", "0008_announcement_search_indexes"),
    ]

    operations = [
        AddIndexIfPostgres(
            model_name="officeresource",
            index=GinIndex(
                SearchVector("title", weight="A", config="english")
                + SearchVector("summary", weight="B", config="english")
                + SearchVector("body", weight="C", config="english"),
                name="office_resource_search_fts",
            ),
        ),
        AddIndexIfPostgres(
            model_name="officeresource",
            index=GinIndex(
                fields=["title"],
                name="office_resource_search_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        AddIndexIfPostgres(
            model_name="user",
            index=GinIndex(
                fields=["first_name", "last_name"],
                name="user_search_name_trgm",
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            ),
        ),
        AddIndexIfPostgres(
            model_name="office",
            index=GinIndex(
                fields=["name"],
                name="office_search_name_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
