"""Signup side-effects: default role + Microsoft Graph profile fields.

``user_signed_up`` fires when allauth creates an account, including the first
Microsoft SSO login. Existing users are left alone.
"""

from allauth.account.signals import user_signed_up
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.dispatch import receiver

from .us import normalize_us_phone


@receiver(user_signed_up)
def assign_default_group(sender, request, user, **kwargs):
    """Add the new user to DEFAULT_USER_GROUP, creating the group if needed."""
    group_name = getattr(settings, "DEFAULT_USER_GROUP", "Users")
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)


@receiver(user_signed_up)
def populate_profile_from_microsoft(sender, request, user, **kwargs):
    """Copy Graph display name / phone onto the user when Microsoft sent them.

    allauth already maps givenName/surname → first_name/last_name. We fill
    display_name (shown in the UI) and phone when Graph has them, so onboarding
    can be pre-filled instead of asking from scratch.
    """
    sociallogin = kwargs.get("sociallogin")
    if sociallogin is None:
        return

    data = sociallogin.account.extra_data or {}
    update_fields: list[str] = []

    display = (data.get("displayName") or "").strip()
    if not display:
        display = " ".join(
            part for part in (user.first_name, user.last_name) if part
        ).strip()
    if display and not user.display_name:
        user.display_name = display[:150]
        update_fields.append("display_name")

    raw_phone = data.get("mobilePhone") or ""
    if not raw_phone:
        phones = data.get("businessPhones") or []
        raw_phone = phones[0] if phones else ""
    if raw_phone and not user.phone_number:
        try:
            user.phone_number = normalize_us_phone(str(raw_phone))
            update_fields.append("phone_number")
        except ValidationError:
            # Graph numbers are not always NANP; leave blank for onboarding.
            pass

    if update_fields:
        user.save(update_fields=update_fields)
