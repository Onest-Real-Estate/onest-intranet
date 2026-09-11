"""Acknowledgement create/idempotency and requirement creation on publish."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.compliance.acknowledgements import (
    acknowledge,
    on_policy_published,
    user_ack_status,
)
from apps.compliance.models import PolicyAcknowledgement, PolicyRequirement
from apps.compliance.tests.factories import agent, publish_policy, publisher


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def test_publish_mandatory_creates_requirement(seeded):
    version = publish_policy(title="Mandatory handbook", is_mandatory=True)
    assert PolicyRequirement.objects.filter(
        policy_version=version, is_active=True
    ).exists()
    status = user_ack_status(agent(), version)
    assert status["required"] is True
    assert status["canAcknowledge"] is True
    assert status["acknowledged"] is False


def test_acknowledge_is_idempotent(seeded):
    version = publish_policy(title="Ack me", is_mandatory=True)
    reader = agent()
    first = acknowledge(
        reader,
        version.pk,
        expected_checksum=version.content_checksum,
        disclosure_version=version.disclosure_version,
    )
    second = acknowledge(
        reader,
        version.pk,
        expected_checksum=version.content_checksum,
        disclosure_version=version.disclosure_version,
    )
    assert first.pk == second.pk
    assert (
        PolicyAcknowledgement.objects.filter(
            user=reader, policy_version=version
        ).count()
        == 1
    )
    status = user_ack_status(reader, version)
    assert status["acknowledged"] is True
    assert status["required"] is False
    assert status["canAcknowledge"] is False


def test_acknowledge_refuses_checksum_mismatch(seeded):
    version = publish_policy(title="Checksum gate", is_mandatory=True)
    reader = agent()
    with pytest.raises(ValidationError):
        acknowledge(
            reader,
            version.pk,
            expected_checksum="deadbeef",
            disclosure_version=version.disclosure_version,
        )


def test_on_policy_published_skips_optional(seeded):
    version = publish_policy(title="Optional", is_mandatory=False)
    assert not PolicyRequirement.objects.filter(policy_version=version).exists()
    on_policy_published(version, publisher())
    assert not PolicyRequirement.objects.filter(policy_version=version).exists()
