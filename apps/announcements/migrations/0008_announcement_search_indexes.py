"""Full-text and trigram indexes for announcement search.

Both are PostgreSQL features and the test suite runs on SQLite, so every
database operation here goes through the conditional wrappers in
``apps.web.search.operations`` and is a no-op elsewhere. The search code picks
its substring path on those backends, which needs no index to be correct.

The GIN expression must match what ``ranking.search_ranked`` builds, weights
included, or PostgreSQL plans a sequential scan and the index is dead weight
nobody notices.
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import migrations

from apps.web.search.operations import (
    AddIndexIfPostgres,
    TrigramExtensionIfPostgres,
)


class Migration(migrations.Migration):
    dependencies = [
        ("announcements", "0007_alter_announcement_cta_url"),
    ]

    operations = [
        TrigramExtensionIfPostgres(),
        AddIndexIfPostgres(
            model_name="announcement",
            index=GinIndex(
                SearchVector("title", weight="A", config="english")
                + SearchVector("summary", weight="B", config="english")
                + SearchVector("body", weight="C", config="english"),
                name="announcement_search_fts",
            ),
        ),
        AddIndexIfPostgres(
            model_name="announcement",
            index=GinIndex(
                fields=["title"],
                name="announcement_search_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
