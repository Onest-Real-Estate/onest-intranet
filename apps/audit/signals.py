"""Wire audit app signal receivers.

Importing this module (done by AuditConfig.ready) ensures the catalog is
loaded so all events are registered before any publisher calls.
"""

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

# Load the catalog so all events are registered at startup.
import apps.audit.catalog  # noqa: F401
from apps.audit.models import AuditEvent
from apps.audit.service import AuditActor, AuditTarget, actor_from_user, log_event


@receiver(user_logged_in)
def audit_user_logged_in(sender, request, user, **kwargs):
    log_event(
        "auth.login.success",
        actor=actor_from_user(user),
        target=AuditTarget(
            target_type="user.user",
            target_id=str(user.pk),
            target_label=str(user),
            target_snapshot={},
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="auth",
        channel="login",
        metadata={"backend": kwargs.get("signal").__class__.__name__},
    )


@receiver(user_login_failed)
def audit_user_login_failed(sender, credentials, request, **kwargs):
    attempted = credentials.get("email") or credentials.get("username") or ""
    log_event(
        "auth.login.failed",
        actor=AuditActor(
            actor_type=AuditEvent.ActorType.ANONYMOUS,
            actor_label="anonymous",
            actor_snapshot={"attempted": attempted},
        ),
        target=AuditTarget(
            target_type="auth.login",
            target_label=attempted,
            target_snapshot={},
        ),
        outcome=AuditEvent.Outcome.DENIED,
        source="auth",
        channel="login",
        reason="authentication_failed",
    )


@receiver(user_logged_out)
def audit_user_logged_out(sender, request, user, **kwargs):
    if user is None:
        return
    log_event(
        "auth.logout",
        actor=actor_from_user(user),
        target=AuditTarget(
            target_type="user.user",
            target_id=str(user.pk),
            target_label=str(user),
            target_snapshot={},
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="auth",
        channel="logout",
    )
