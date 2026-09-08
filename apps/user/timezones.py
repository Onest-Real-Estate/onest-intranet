from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_iana_timezone(value: str) -> None:
    if value != "UTC" and "/" not in value:
        raise ValidationError(
            _("Use a regional IANA timezone such as America/New_York.")
        )
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValidationError(_("Enter a valid IANA timezone name.")) from exc
