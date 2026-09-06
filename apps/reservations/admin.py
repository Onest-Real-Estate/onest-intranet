from django.contrib import admin

from apps.reservations.models import (
    Amenity,
    Space,
    SpaceAmenity,
    SpaceAvailabilityException,
    SpaceOfficeTransfer,
    SpacePhoto,
    WeeklyAvailability,
)

admin.site.register(Amenity)
admin.site.register(Space)
admin.site.register(SpaceAmenity)
admin.site.register(SpacePhoto)
admin.site.register(WeeklyAvailability)
admin.site.register(SpaceAvailabilityException)
admin.site.register(SpaceOfficeTransfer)
