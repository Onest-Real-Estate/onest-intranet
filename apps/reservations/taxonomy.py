from enum import StrEnum

from django.db import models
from django.utils.translation import gettext_lazy as _


class SpaceType(models.TextChoices):
    CONFERENCE_ROOM = "conference_room", _("Conference room")
    MEETING_ROOM = "meeting_room", _("Meeting room")
    TRAINING_ROOM = "training_room", _("Training room")
    PRIVATE_OFFICE = "private_office", _("Private office")
    COWORKING_AREA = "coworking_area", _("Coworking area")
    EVENT_SPACE = "event_space", _("Event space")
    STUDIO = "studio", _("Studio")
    OTHER = "other", _("Other")


class SpaceStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    INACTIVE = "inactive", _("Inactive")
    RETIRED = "retired", _("Retired")


class RecurrencePolicy(models.TextChoices):
    NONE = "none", _("Recurring bookings not allowed")
    WEEKLY = "weekly", _("Weekly recurrence allowed")
    DAILY_OR_WEEKLY = "daily_or_weekly", _("Daily or weekly recurrence allowed")


class AmenityCategory(models.TextChoices):
    ACCESSIBILITY = "accessibility", _("Accessibility")
    AUDIO_VISUAL = "audio_visual", _("Audio and visual")
    CONNECTIVITY = "connectivity", _("Connectivity")
    FURNISHINGS = "furnishings", _("Furnishings")
    FOOD_BEVERAGE = "food_beverage", _("Food and beverage")
    PRIVACY = "privacy", _("Privacy")
    OTHER = "other", _("Other")


class Weekday(models.IntegerChoices):
    MONDAY = 0, _("Monday")
    TUESDAY = 1, _("Tuesday")
    WEDNESDAY = 2, _("Wednesday")
    THURSDAY = 3, _("Thursday")
    FRIDAY = 4, _("Friday")
    SATURDAY = 5, _("Saturday")
    SUNDAY = 6, _("Sunday")


class ExceptionKind(models.TextChoices):
    HOLIDAY = "holiday", _("Holiday")
    MAINTENANCE = "maintenance", _("Maintenance")
    CLOSURE = "closure", _("Closure")
    ADMIN_HOLD = "admin_hold", _("Administrative hold")


class ExceptionVisibility(models.TextChoices):
    PUBLIC = "public", _("Visible to agents")
    INTERNAL = "internal", _("Internal only")


class SpacePermission(StrEnum):
    VIEW = "reservations.view_spaces"
    MANAGE = "reservations.manage_spaces"
    MANAGE_SCHEDULE = "reservations.manage_space_schedules"
    VIEW_SENSITIVE = "reservations.view_space_sensitive"


class WallTimeBoundary(StrEnum):
    START = "start"
    END = "end"
