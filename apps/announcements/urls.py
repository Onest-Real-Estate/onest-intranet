from django.urls import path

from .views import announcements

urlpatterns = [
    path("announcements", announcements, name="announcements"),
]
