"""Drift between the migration recorder and the files on disk (#204)."""

import pytest
from django.core.management import CommandError, call_command
from django.db import connections
from django.db.migrations.recorder import MigrationRecorder

PHANTOM_APP = "user"
PHANTOM_NAME = "0099_phantom_from_feature_branch"


@pytest.mark.django_db
def test_clean_database_reports_no_drift():
    call_command("check_migration_drift")


@pytest.mark.django_db
def test_phantom_fails_until_pruned():
    recorder = MigrationRecorder(connections["default"])
    recorder.record_applied(PHANTOM_APP, PHANTOM_NAME)

    with pytest.raises(CommandError, match="1 phantom"):
        call_command("check_migration_drift")

    call_command("check_migration_drift", prune=True)
    assert not recorder.migration_qs.filter(app=PHANTOM_APP, name=PHANTOM_NAME).exists()
    call_command("check_migration_drift")


@pytest.mark.django_db
def test_duplicate_recorder_rows_pruned_to_one():
    recorder = MigrationRecorder(connections["default"])
    recorder.record_applied("contenttypes", "0001_initial")
    recorder.record_applied("contenttypes", "0001_initial")

    with pytest.raises(CommandError, match="duplicate"):
        call_command("check_migration_drift")

    call_command("check_migration_drift", prune=True)
    assert (
        recorder.migration_qs.filter(app="contenttypes", name="0001_initial").count()
        == 1
    )
