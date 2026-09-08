from django.http import HttpResponse
from django.urls import path


def unclassified_view(request):
    return HttpResponse("unclassified")


urlpatterns = [
    path("unclassified", unclassified_view),
]
